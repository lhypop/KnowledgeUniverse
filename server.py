#!/usr/bin/env python3
"""
Knowledge Universe — 文献知识宇宙 Web 服务
统一界面：文献获取 / 总结分析 / 关联组织 / 订阅管理

启动: python server.py
访问: http://localhost:8900
"""

import http.server
import json
import os
import re
import sqlite3
import sys
import threading
import urllib.parse
from pathlib import Path
from datetime import datetime

# ─── Configuration ───────────────────────────────────────────
PORT = 8900
DB_PATH = os.path.expanduser("~/.hermes/data/lit_tracker.db")
STATIC_DIR = Path(__file__).parent
SCRIPTS_DIR = os.path.expanduser("~/.hermes/scripts")

sys.path.insert(0, SCRIPTS_DIR)

# ─── Database Helpers ────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

def paper_row_to_dict(row):
    d = dict(row)
    for field in ['authors', 'categories', 'tags', 'key_findings', 'external_ids']:
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d

# ─── API Handlers ────────────────────────────────────────────

def api_papers(params, body):
    """GET /api/papers — 列出论文"""
    conn = get_conn()
    conditions = []
    sql_params = []

    status = params.get('status', [''])[0]
    starred = params.get('starred', [''])[0]
    tag = params.get('tag', [''])[0]
    search = params.get('search', [''])[0]
    limit = int(params.get('limit', ['50'])[0])
    offset = int(params.get('offset', ['0'])[0])

    if status:
        conditions.append("status = ?")
        sql_params.append(status)
    if starred == '1':
        conditions.append("is_starred = 1")
    if tag:
        conditions.append("tags LIKE ?")
        sql_params.append(f'%"{tag}"%')
    if search:
        conditions.append("(title LIKE ? OR abstract LIKE ?)")
        sql_params.extend([f'%{search}%', f'%{search}%'])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT id, arxiv_id, title, authors, published_date, primary_category,
               citation_count, status, is_starred, rating, summary_cn, tags, source, pdf_url
        FROM papers {where}
        ORDER BY published_date DESC
        LIMIT ? OFFSET ?
    """
    sql_params.extend([limit + 1, offset])
    rows = conn.execute(query, sql_params).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]

    papers = []
    for r in rows:
        p = dict(r)
        for field in ['authors', 'tags']:
            if p.get(field):
                try:
                    p[field] = json.loads(p[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        papers.append(p)

    count_query = f"SELECT COUNT(*) as cnt FROM papers {where}"
    total = conn.execute(count_query, sql_params[:-2]).fetchone()['cnt']
    conn.close()

    return {'papers': papers, 'total': total, 'has_more': has_more}, 200, None


def api_paper_detail(paper_id, params, body):
    """GET /api/paper/<id> — 论文详情 + 关联论文"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not row:
        conn.close()
        return None, 404, "论文不存在"

    paper = paper_row_to_dict(row)

    rels = conn.execute("""
        SELECT pr.*, p.title as related_title, p.arxiv_id as related_arxiv_id,
               p.authors as related_authors, p.published_date as related_date
        FROM paper_relations pr
        JOIN papers p ON pr.related_paper_id = p.id
        WHERE pr.paper_id = ?
        ORDER BY pr.strength DESC
    """, (paper_id,)).fetchall()

    paper['relations'] = [dict(r) for r in rels]
    conn.close()
    return paper, 200, None


def api_paper_star(paper_id, params, body):
    """POST /api/paper/<id>/star — 切换收藏"""
    conn = get_conn()
    row = conn.execute("SELECT is_starred FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not row:
        conn.close()
        return None, 404, "论文不存在"
    new_val = 0 if row['is_starred'] else 1
    conn.execute("UPDATE papers SET is_starred = ? WHERE id = ?", (new_val, paper_id))
    conn.commit()
    conn.close()
    return {'is_starred': bool(new_val)}, 200, None


def api_paper_status(paper_id, params, body):
    """POST /api/paper/<id>/status — 更新状态"""
    status = body.get('status', 'read')
    if status not in ('new', 'read', 'archived', 'skipped'):
        return None, 400, "无效状态"
    conn = get_conn()
    conn.execute("UPDATE papers SET status = ? WHERE id = ?", (status, paper_id))
    conn.commit()
    conn.close()
    return {'status': status}, 200, None


def api_paper_rate(paper_id, params, body):
    """POST /api/paper/<id>/rate — 评分"""
    rating = body.get('rating', 0)
    conn = get_conn()
    conn.execute("UPDATE papers SET rating = ? WHERE id = ?", (int(rating), paper_id))
    conn.commit()
    conn.close()
    return {'rating': int(rating)}, 200, None


def api_paper_tag(paper_id, params, body):
    """POST /api/paper/<id>/tag — 更新标签"""
    tags = body.get('tags', [])
    conn = get_conn()
    conn.execute("UPDATE papers SET tags = ? WHERE id = ?", (json.dumps(tags, ensure_ascii=False), paper_id))
    conn.commit()
    conn.close()
    return {'tags': tags}, 200, None


def api_paper_note(paper_id, params, body):
    """POST /api/paper/<id>/note — 更新笔记"""
    note = body.get('note', '')
    conn = get_conn()
    conn.execute("UPDATE papers SET notes = ? WHERE id = ?", (note, paper_id))
    conn.commit()
    conn.close()
    return {'notes': note}, 200, None


def api_paper_obsidian(paper_id, params, body):
    """POST /api/paper/<id>/obsidian — 生成 Obsidian 笔记"""
    try:
        from lit_tracker.cli import create_paper_note_func
        path = create_paper_note_func(paper_id)
        return {'obsidian_path': path}, 200, None
    except Exception as e:
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, 'lit_tracker_run.py'), 'obsidian', str(paper_id)],
            capture_output=True, text=True, timeout=30
        )
        return {'obsidian_path': result.stdout.strip(), 'error': result.stderr if result.returncode != 0 else None}, 200, None


def api_paper_relations(paper_id, params, body):
    """POST /api/paper/<id>/relations — 添加/更新关联"""
    conn = get_conn()
    related_id = body.get('related_paper_id')
    rel_type = body.get('relation_type', 'related')
    context = body.get('context', '')
    strength = body.get('strength', 0.5)

    existing = conn.execute(
        "SELECT id FROM paper_relations WHERE paper_id = ? AND related_paper_id = ?",
        (paper_id, related_id)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE paper_relations SET relation_type=?, context=?, strength=? WHERE id=?",
            (rel_type, context, strength, existing['id'])
        )
    else:
        conn.execute(
            "INSERT INTO paper_relations (paper_id, related_paper_id, relation_type, context, strength) VALUES (?,?,?,?,?)",
            (paper_id, related_id, rel_type, context, strength)
        )
    conn.commit()
    conn.close()
    return {'status': 'ok'}, 200, None


# ─── Subscription API ────────────────────────────────────────

def api_subscriptions_list(params, body):
    """GET /api/subscriptions"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, name, type, query, source, max_results, frequency, active, last_scan, last_count, notes
        FROM subscriptions ORDER BY active DESC, name
    """).fetchall()
    conn.close()
    return {'subscriptions': [dict(r) for r in rows]}, 200, None


def api_subscriptions_add(params, body):
    """POST /api/subscriptions — 添加订阅"""
    name = body.get('name', '')
    sub_type = body.get('type', 'topic')
    query = body.get('query', '')
    source = body.get('source', 'arxiv')
    max_results = body.get('max_results', 10)
    frequency = body.get('frequency', 'daily')

    if not name or not query:
        return None, 400, "名称和查询不能为空"

    conn = get_conn()
    conn.execute("""
        INSERT INTO subscriptions (name, type, query, source, max_results, frequency, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
    """, (name, sub_type, query, source, max_results, frequency, now_iso()))
    conn.commit()
    sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {'id': sub_id, 'name': name}, 201, None


def api_subscription_delete(sub_id, params, body):
    """DELETE /api/subscription/<id>"""
    conn = get_conn()
    conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    conn.commit()
    conn.close()
    return {'status': 'deleted'}, 200, None


def api_subscription_toggle(sub_id, params, body):
    """POST /api/subscription/<id>/toggle"""
    conn = get_conn()
    row = conn.execute("SELECT active FROM subscriptions WHERE id = ?", (sub_id,)).fetchone()
    if not row:
        conn.close()
        return None, 404, "订阅不存在"
    new_val = 0 if row['active'] else 1
    conn.execute("UPDATE subscriptions SET active = ? WHERE id = ?", (new_val, sub_id))
    conn.commit()
    conn.close()
    return {'active': bool(new_val)}, 200, None


# ─── Action API ───────────────────────────────────────────────

def api_search(params, body):
    """POST /api/search — 搜索 arXiv"""
    query = body.get('query', '')
    max_results = body.get('max_results', 10)
    if not query:
        return None, 400, "搜索词不能为空"

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, 'lit_tracker_run.py'), 'search', query, '--max', str(max_results)],
            capture_output=True, text=True, timeout=60
        )
        from lit_tracker.cli import quick_search
        quick_search(query, max_results)
        return {'output': result.stdout, 'new_papers': result.stdout.count('new')}, 200, None
    except Exception as e:
        return {'error': str(e)}, 500, None


def api_scan_all(params, body):
    """POST /api/scan"""
    try:
        from lit_tracker.cli import scan_all
        result = scan_all()
        return result, 200, None
    except Exception as e:
        return {'error': str(e)}, 500, None


def api_summarize(params, body):
    """POST /api/summarize — 触发总结"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title FROM papers
        WHERE (summary_cn IS NULL OR summary_cn = '') AND status = 'new'
        ORDER BY published_date DESC LIMIT 10
    """).fetchall()
    conn.close()
    return {'papers_needing_summary': [{'id': r['id'], 'title': r['title']} for r in rows]}, 200, None


def api_save_summary(paper_id, params, body):
    """POST /api/paper/<id>/summary — 保存总结"""
    summary_cn = body.get('summary_cn', '')
    key_findings = body.get('key_findings', [])
    conn = get_conn()
    conn.execute(
        "UPDATE papers SET summary_cn = ?, key_findings = ? WHERE id = ?",
        (summary_cn, json.dumps(key_findings, ensure_ascii=False), paper_id)
    )
    conn.commit()
    conn.close()
    return {'status': 'saved'}, 200, None


# ─── Stats API ────────────────────────────────────────────────

def api_stats(params, body):
    """GET /api/stats"""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) as cnt FROM papers").fetchone()['cnt']
    new_count = conn.execute("SELECT COUNT(*) as cnt FROM papers WHERE status='new'").fetchone()['cnt']
    starred = conn.execute("SELECT COUNT(*) as cnt FROM papers WHERE is_starred=1").fetchone()['cnt']
    read_count = conn.execute("SELECT COUNT(*) as cnt FROM papers WHERE status='read'").fetchone()['cnt']

    cats = conn.execute("""
        SELECT primary_category, COUNT(*) as cnt FROM papers
        GROUP BY primary_category ORDER BY cnt DESC LIMIT 10
    """).fetchall()

    authors = conn.execute("""
        SELECT authors, COUNT(*) as cnt FROM papers
        WHERE authors IS NOT NULL
        GROUP BY authors ORDER BY cnt DESC LIMIT 10
    """).fetchall()

    monthly = conn.execute("""
        SELECT substr(published_date, 1, 7) as month, COUNT(*) as cnt
        FROM papers GROUP BY month ORDER BY month DESC LIMIT 12
    """).fetchall()

    cited = conn.execute("SELECT COUNT(*) as cnt FROM papers WHERE citation_count > 0").fetchone()['cnt']
    high_cited = conn.execute("SELECT COUNT(*) as cnt FROM papers WHERE citation_count >= 10").fetchone()['cnt']
    avg_citations = conn.execute("SELECT AVG(citation_count) FROM papers WHERE citation_count IS NOT NULL").fetchone()[0] or 0

    sub_count = conn.execute("SELECT COUNT(*) as cnt FROM subscriptions WHERE active=1").fetchone()['cnt']
    total_subs = conn.execute("SELECT COUNT(*) as cnt FROM subscriptions").fetchone()['cnt']
    conn.close()

    return {
        'total_papers': total,
        'new_papers': new_count,
        'starred_papers': starred,
        'read_papers': read_count,
        'categories': [{'name': c['primary_category'], 'count': c['cnt']} for c in cats],
        'top_authors': [{'name': a['authors'], 'count': a['cnt']} for a in authors],
        'monthly_trend': [{'month': m['month'], 'count': m['cnt']} for m in monthly],
        'cited_papers': cited,
        'high_cited': high_cited,
        'avg_citations': round(avg_citations, 1),
        'active_subscriptions': sub_count,
        'total_subscriptions': total_subs,
    }, 200, None


# ─── Router ───────────────────────────────────────────────────

API_ROUTES = [
    (r'^/api/papers$', 'GET', api_papers),
    (r'^/api/paper/(\d+)$', 'GET', api_paper_detail),
    (r'^/api/paper/(\d+)/star$', 'POST', api_paper_star),
    (r'^/api/paper/(\d+)/status$', 'POST', api_paper_status),
    (r'^/api/paper/(\d+)/rate$', 'POST', api_paper_rate),
    (r'^/api/paper/(\d+)/tag$', 'POST', api_paper_tag),
    (r'^/api/paper/(\d+)/note$', 'POST', api_paper_note),
    (r'^/api/paper/(\d+)/obsidian$', 'POST', api_paper_obsidian),
    (r'^/api/paper/(\d+)/relations$', 'POST', api_paper_relations),
    (r'^/api/paper/(\d+)/summary$', 'POST', api_save_summary),
    (r'^/api/subscriptions$', 'GET', api_subscriptions_list),
    (r'^/api/subscriptions$', 'POST', api_subscriptions_add),
    (r'^/api/subscription/(\d+)$', 'DELETE', api_subscription_delete),
    (r'^/api/subscription/(\d+)/toggle$', 'POST', api_subscription_toggle),
    (r'^/api/search$', 'POST', api_search),
    (r'^/api/scan$', 'POST', api_scan_all),
    (r'^/api/summarize$', 'POST', api_summarize),
    (r'^/api/stats$', 'GET', api_stats),
]


def route_api(path, method, body=None):
    for pattern, http_method, handler in API_ROUTES:
        m = re.match(pattern, path)
        if m and method == http_method:
            try:
                if m.lastindex:
                    result, status, error = handler(*m.groups(), {}, body or {})
                else:
                    result, status, error = handler({}, body or {})
                if error:
                    return json.dumps({'error': error}, ensure_ascii=False), status
                return json.dumps(result, ensure_ascii=False, default=str), status
            except Exception as e:
                return json.dumps({'error': str(e)}, ensure_ascii=False), 500
    return json.dumps({'error': 'Not Found'}, ensure_ascii=False), 404


# ─── HTTP Server ──────────────────────────────────────────────

class KnowledgeUniverseHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path.startswith('/api/'):
            self._send_api_response(route_api(path, 'GET'))
            return

        if path == '/' or path == '':
            path = '/index.html'

        file_path = STATIC_DIR / path.lstrip('/')
        if file_path.exists() and file_path.is_file():
            self._serve_file(file_path)
        else:
            self._serve_file(STATIC_DIR / 'index.html')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not path.startswith('/api/'):
            self.send_error(404)
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length > 0:
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {}

        self._send_api_response(route_api(path, 'POST', body))

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith('/api/'):
            self._send_api_response(route_api(path, 'DELETE'))
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.end_headers()

    def _send_api_response(self, response_data):
        body, status = response_data
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._send_cors()
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def _send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _serve_file(self, file_path):
        content_type_map = {
            '.html': 'text/html; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.json': 'application/json; charset=utf-8',
            '.svg': 'image/svg+xml',
            '.png': 'image/png',
            '.ico': 'image/x-icon',
        }
        ext = file_path.suffix.lower()
        content_type = content_type_map.get(ext, 'application/octet-stream')

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def log_message(self, format, *args):
        pass


def main():
    server = http.server.ThreadingHTTPServer(('0.0.0.0', PORT), KnowledgeUniverseHandler)
    print(f"🌌 Knowledge Universe 启动!")
    print(f"   http://localhost:{PORT}")
    print(f"   按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务已停止")


if __name__ == '__main__':
    main()
