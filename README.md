# 🌌 Knowledge Universe — 文献知识宇宙

AI 驱动的文献获取、总结分析、关联组织与订阅管理 Web 平台。

## 功能

- **📄 论文库** — 浏览、搜索、过滤论文库，查看摘要、AI 总结、收藏评分、标签管理
- **📡 订阅管理** — 添加/管理 arXiv 订阅（关键词、分类、作者），自动扫描新论文
- **📊 统计分析** — 分类分布、月度趋势、高产作者、引用分析
- **🔗 关联组织** — 论文间关联关系管理
- **📝 Obsidian 集成** — 一键导出论文笔记到 Obsidian

## 快速启动

```bash
python server.py
# 访问 http://localhost:8900
```

## 依赖

- Python 3.8+
- SQLite3 (内置)
- lit-tracker (Hermes Agent 文献追踪脚本)

## 数据

共用 `~/.hermes/data/lit_tracker.db` 数据库，与 Hermes Agent 文献追踪系统互通。
