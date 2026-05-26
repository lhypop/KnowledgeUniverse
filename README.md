# 🌌 Knowledge Universe — 文献知识宇宙

AI 驱动的文献获取、总结分析、关联组织与订阅管理 Web 平台。

## 🔗 访问地址

- **Demo 预览**: https://lhypop.github.io/KnowledgeUniverse/
- **本地完整版**: `http://localhost:8900`（运行 `python server.py`）

## ✨ 功能

### 📄 论文库
- 浏览、搜索、过滤论文库
- 论文详情弹窗：摘要、AI 总结、标签、评分
- 收藏 / 已读状态管理
- 论文笔记编辑
- Obsidian 一键导出

### 📡 订阅管理
- 添加/管理 arXiv 订阅（关键词、分类、作者）
- 一键扫描新论文
- 启用/停用订阅

### 📊 统计分析
- 总览面板（论文数、未读、收藏、引用）
- 分类分布图
- 月度趋势图
- 高产作者排行

### 🔗 关联组织
- 论文间关联关系管理
- 引用/构建于/后继 关系

## 🚀 快速启动

```bash
# 启动服务
python server.py

# 访问
open http://localhost:8900
```

## 📦 依赖

- Python 3.8+
- SQLite3（内置）
- lit-tracker（Hermes Agent 文献追踪脚本）
- 数据共用 `~/.hermes/data/lit_tracker.db`

## 🌐 部署

### 本地（完整功能）
```bash
git clone https://github.com/lhypop/KnowledgeUniverse.git
cd KnowledgeUniverse
python server.py
```

### GitHub Pages（Demo）
仓库已配置 `docs/` 目录自动部署，访问 https://lhypop.github.io/KnowledgeUniverse/

### 公网部署（免费）
推荐使用 [Render](https://render.com) 免费计划部署 Python Web 服务：
1. Fork 此仓库
2. 在 Render 新建 Web Service，连接 GitHub
3. 设置 Start Command: `python server.py`

## 📁 项目结构

```
KnowledgeUniverse/
├── server.py          # Python API 服务 (16 REST 端点)
├── index.html         # 完整 SPA 前端
├── docs/
│   └── index.html     # GitHub Pages Demo（内置模拟数据）
└── README.md
```
