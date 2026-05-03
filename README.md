# 本项目为北京邮电大学程序设计综合实践课程项目，目前正处于敏捷开发阶段，核心 RAG 链路与多 Agent 架构正在逐步提交中...

# Mini-NotebookLM

> 面向大学生的多模态课程知识库与 AI 辅导系统
>
> 课程设计项目 · 09班李宇 2022210347

---

## 项目简介

Mini-NotebookLM 是一款运行在本地 Windows 环境的 **知识库工作台**。用户可以把课程 PDF、PPT、Word 等文档上传到独立的知识库空间，由 MinerU 在线 API 解析后，经过自研的 IR 中间格式标准化、结构感知切片与向量索引，最终通过混合检索 + 重排序 + 多模态大模型实现高质量的文档问答。

本项目的核心工程主线：

```
原始文档 → MinerU 解析 → IR 标准化 → Parent/Child 切片 → 向量 + 关键词索引 → 混合检索 → 重排序 → 多模态问答
```

> **当前版本**：已完成 Stage 1–5 基础链路，并完成 Stage 7 收口（文档一致性、文件夹上传、批量操作、bbox 高亮定位）。

---

## 功能概览

### 已实现

| 功能 | 说明 |
|------|------|
| 多知识库空间管理 | 创建、删除知识库；每个知识库独立管理文件和向量索引 |
| 多格式文档上传 | 支持 PDF、PPT/PPTX、Word/DOCX、图片（MinerU 支持的格式） |
| MinerU 异步解析 | 调用 MinerU 在线 API (vlm 模型)，下载 zip，解析 content_list_v2.json + layout.json |
| 自研 IR 标准化 | DOM 重建、header_path 注入、多模态块建模、坐标锚点保留 |
| 结构感知切片 | Parent/Child 双层切片，不跨标题边界，list/code 保留原子性 |
| 多模态富化 | 图片/表格调用 qwen3.5-flash 生成描述/摘要，用于检索阶段 |
| 混合向量索引 | text-embedding-v4 (1024维) 向量存入 Qdrant；SQLite FTS5 关键词索引 |
| 混合检索 + RRF | 向量召回 + BM25 关键词召回并行，RRF 融合排序 |
| 重排序 | qwen3-rerank 对候选结果二次打分 |
| 流式多模态问答 | qwen3.5-plus；SSE 流式输出；支持 thinking 模式 |
| 引用溯源 | 每条回答携带引用列表（文档、章节、页码） |
| PDF 原文预览 + bbox 高亮 | 引用面板"查看原文"，使用 react-pdf 定位页码并叠加 bbox 高亮框 |
| 文件夹上传 | 支持上传整目录，保留 relative_path 逻辑路径 |
| 批量操作 | 支持全选后批量删除、批量重解析 |
| 任务状态监控 | 实时查看解析/索引任务状态、进度与错误信息 |
| MinerU 警告提示 | 若 MinerU 返回异常字段或降级，前端黄色警告提醒用户复查 |

### 暂未实现（提升项）

- 音视频转写（飞书妙记 / 通义听悟）
- 视频关键帧方案
- 目录树浏览与文件夹展开/收起
- 文件夹删除 / 文件夹重命名 / 文件移动
- 文件重命名 / 移动
- 按文件类型筛选
- 设置页（API Key 在线编辑）

---

## 技术栈

### 后端

| 组件 | 选型 | 说明 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | 异步 API 服务 |
| 数据校验 | Pydantic v2 | Schema First，贯穿 IR / Chunk 全流程 |
| 向量数据库 | Qdrant (本地文件模式) | 存储 Child Chunk 向量 |
| 关系数据库 | SQLite + FTS5 | 文档元数据、任务状态、Parent/Child 映射、关键词索引 |
| 文档解析 | MinerU 在线 API (vlm) | PDF/PPT/Word/图片 → content_list_v2.json + layout.json |
| 向量模型 | text-embedding-v4 (阿里云百炼) | 1024维，纯文本嵌入 |
| 重排序 | qwen3-rerank (阿里云百炼) | 候选 chunk 二次打分 |
| 视觉小模型 | qwen3.5-flash (阿里云百炼) | 图片描述 / 表格摘要 |
| 问答模型 | qwen3.5-plus (阿里云百炼) | 最终多模态问答，SSE 流式输出 |
| HTTP 客户端 | httpx | 与 MinerU / DashScope API 通信 |

### 前端

| 组件 | 选型 |
|------|------|
| 框架 | React 19 + Vite |
| 样式 | Tailwind CSS v4 |
| 路由 | React Router v7 |
| Markdown 渲染 | react-markdown + remark-gfm |
| 图标 | lucide-react |
| PDF 预览 | react-pdf |
| SSE 流式 | fetch + ReadableStream (非 EventSource) |

---

## 目录结构

```
mini-notebooklm/
├── backend/
│   ├── app/
│   │   ├── adapters/          # MinerU zip 解析与 IR 标准化层
│   │   │   ├── bundle_parser.py   # 解压 zip，提取 content_list_v2.json / layout.json / images
│   │   │   ├── dom_builder.py     # DOM 树重建，注入 header_path
│   │   │   ├── normalizer.py      # Raw MinerU → 标准 IR Block
│   │   │   └── footnote_linker.py # 脚注关联
│   │   ├── api/               # FastAPI 路由
│   │   │   ├── kb.py              # 知识库 CRUD
│   │   │   ├── documents.py       # 文件上传、解析触发、删除、origin-pdf
│   │   │   ├── chat.py            # 流式问答、搜索
│   │   │   ├── tasks.py           # 任务状态查询
│   │   │   └── health.py          # 健康检查
│   │   ├── chunkers/          # Parent / Child 切片
│   │   │   ├── parent_chunker.py
│   │   │   └── child_chunker.py
│   │   ├── db/                # 数据库初始化与客户端
│   │   │   ├── database.py        # SQLite 建表、FTS5、懒迁移
│   │   │   └── qdrant_client.py   # Qdrant 集合初始化
│   │   ├── enrichers/         # 多模态富化（图片描述 / 表格摘要）
│   │   ├── models/            # Pydantic 模型
│   │   │   ├── models_raw_mineru.py   # MinerU 原始输出 Schema
│   │   │   ├── models_ir.py           # 自研 IR 中间格式 Schema
│   │   │   └── models_chunk.py        # Parent / Child Chunk Schema
│   │   ├── services/          # 业务服务
│   │   │   ├── pipeline_service.py    # 全流程编排（上传→解析→IR→切片→索引）
│   │   │   ├── mineru_client.py       # MinerU API 客户端
│   │   │   ├── embedding_service.py   # text-embedding-v4 向量化
│   │   │   ├── index_service.py       # Qdrant + SQLite FTS5 入库
│   │   │   ├── retrieval_service.py   # 混合检索 + RRF 融合
│   │   │   ├── rerank_service.py      # qwen3-rerank 重排序
│   │   │   └── qa_service.py          # qwen3.5-plus 流式问答
│   │   ├── validators/        # IR / Chunk 结构校验
│   │   ├── writers/           # IR / Chunk JSONL 落盘
│   │   ├── config.py          # 全局配置（pydantic-settings）
│   │   └── main.py            # FastAPI 应用入口
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .env.example           # 环境变量模板
│   ├── test_stage2.py         # MinerU 解析与 IR 单元测试
│   ├── test_stage3.py         # 切片与索引单元测试
│   └── test_stage4.py         # 检索与问答端到端测试
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts          # 所有后端 API 调用封装
│   │   │   └── types.ts           # TypeScript 接口定义
│   │   ├── components/
│   │   │   ├── Layout.tsx         # 左侧主导航布局
│   │   │   └── ui/                # 基础 UI 组件
│   │   │       ├── alert.tsx      # 含 warning (黄色) 变体
│   │   │       ├── badge.tsx
│   │   │       ├── button.tsx
│   │   │       ├── card.tsx
│   │   │       ├── dialog.tsx
│   │   │       ├── input.tsx
│   │   │       ├── progress.tsx   # 支持不定进度动画
│   │   │       ├── separator.tsx
│   │   │       ├── spinner.tsx
│   │   │       └── textarea.tsx
│   │   ├── pages/
│   │   │   ├── KnowledgeBasePage.tsx   # 知识库首页（卡片网格）
│   │   │   ├── KBFilesPage.tsx         # 文件管理页（文件/文件夹上传 + 批量操作 + 状态/警告）
│   │   │   ├── ChatPage.tsx            # 对话问答页（SSE + 引用面板 + PDF bbox 高亮）
│   │   │   ├── TasksPage.tsx           # 任务监控页
│   │   │   └── SettingsPage.tsx        # 设置页（占位，待实现）
│   │   ├── lib/utils.ts
│   │   ├── index.css
│   │   ├── App.tsx                # 路由配置
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── data/                      # 运行时数据（不纳入版本控制）
│   ├── sqlite/                # SQLite 数据库
│   ├── qdrant_storage/        # Qdrant 向量存储
│   ├── uploads/               # 原始上传文件
│   ├── mineru_zips/           # MinerU 返回压缩包
│   └── rag_output/            # IR JSON / Chunk JSONL / 图片
│
├── doc/                       # 项目文档
│   ├── 09班李宇2022210347-本地ai知识库需求分析报告V7.md
│   ├── MinerU to RAG Pipeline 架构设计与数据流方案.md
│   └── 在线API输出文件格式（SaaS推断版）.md
│
└── test_inputs/               # 测试用样本文件
    ├── sample.pdf
    ├── sample.docx
    └── sample.pptx
```

---

## 快速开始

### 前置依赖

- Python 3.11+
- Node.js 18+
- MinerU 在线 API Key（[申请地址](https://mineru.net)）
- 阿里云百炼 API Key（[申请地址](https://bailian.console.aliyun.com)）

### 1. 克隆项目

```bash
git clone <repo-url>
cd mini-notebooklm
```

### 2. 后端配置

```bash
cd backend

# 安装依赖（创建/更新 .venv）
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入以下两个 Key：
#   MINERU_API_KEY=your_mineru_key
#   ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_dashscope_key
```

### 3. 启动后端

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端启动后会自动创建 `data/` 下所有目录、初始化 SQLite 数据库和 Qdrant 向量集合。

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:5173`，已配置代理将 `/api` 转发至 `http://127.0.0.1:8000`。

### 5. 访问

打开浏览器访问 `http://localhost:5173`。

---

## 使用流程

1. **新建知识库**：在首页点击「新建知识库」，输入名称和描述
2. **上传文件/文件夹**：进入知识库文件管理页，支持拖拽上传、文件上传、整文件夹上传
3. **等待解析**：系统自动触发 MinerU 解析，实时展示解析状态（约 15–60 秒/文件）
4. **开始对话**：解析完成后点击「开始对话」，向知识库提问
5. **查看引用**：回答右侧引用面板展示命中来源；点击「查看原文」可预览 PDF，并对命中 bbox 高亮

### 文档状态说明

| 状态 | 含义 |
|------|------|
| `已上传` | 文件上传成功，等待解析 |
| `解析中` | MinerU 解析 + IR 标准化 + 切片 + 索引进行中 |
| `已索引` | 全流程完成，可供问答 |
| `需检视` ⚠️ | MinerU 返回了未知字段或结构降级警告，文档已入库但建议复查 |
| `失败` | 解析或入库失败，可点击重新解析 |

---

## API 文档

后端服务启动后，访问 `http://127.0.0.1:8000/docs` 查看自动生成的 Swagger UI。

### 主要端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/kb` | 列出所有知识库 |
| `POST` | `/api/kb` | 创建知识库 |
| `DELETE` | `/api/kb/{kb_id}` | 删除知识库（含所有文档和向量） |
| `GET` | `/api/documents/{kb_id}` | 列出知识库内文档 |
| `POST` | `/api/documents/{kb_id}/upload` | 上传文件（支持 `relative_path`，用于文件夹上传） |
| `POST` | `/api/documents/{kb_id}/{doc_id}/parse` | 触发解析（支持重新解析） |
| `DELETE` | `/api/documents/{kb_id}/{doc_id}` | 删除文档（含向量和文件） |
| `GET` | `/api/documents/{kb_id}/{doc_id}/origin-pdf` | 获取 origin.pdf 原文 |
| `POST` | `/api/chat/{kb_id}` | 流式问答（SSE） |
| `POST` | `/api/chat/{kb_id}/search` | 纯检索（不生成回答） |
| `GET` | `/api/tasks` | 列出最近任务 |
| `GET` | `/api/tasks/doc/{doc_id}` | 列出指定文档的任务 |
| `GET` | `/api/health` | 健康检查 |

---

## 环境变量说明

参见 `backend/.env.example`：

```env
# MinerU 在线 API
MINERU_API_KEY=

# 阿里云百炼（DashScope）
ALIBABA_CLOUD_ACCESS_KEY_SECRET=
```

所有其他配置（模型名称、路径、Chunking 参数等）在 `backend/app/config.py` 中有默认值，无需修改即可运行。

---

## 核心设计说明

### IR 中间格式

系统不直接将 MinerU 原始输出送入向量库，而是经过自研 IR 标准化层处理：

1. `bundle_parser.py` 解压 MinerU zip，提取 `content_list_v2.json`、`layout.json`、`*_origin.pdf`、`images/`
2. `normalizer.py` 将 MinerU Raw Block 转为标准 `IRBlock`（统一字段名，类型归一化）
3. `dom_builder.py` 重建文档 DOM 树，为每个块注入 `header_path`（标题路径链）
4. 输出 `document_ir.json` 落盘，供切片层使用

### Parent / Child 切片策略

- **Child Chunk**（150–250 token）：面向向量检索，用于召回
- **Parent Chunk**：以小节为粒度的大块，用于回答阶段补全上下文
- 不跨越 H1/H2 等标题边界
- `list`、`code` 保留原子性，不拆分

### 混合检索

```
用户查询
├── 向量检索（Qdrant cosine similarity）
├── BM25 关键词检索（SQLite FTS5）
└──  RRF 融合 → qwen3-rerank 重排序 → Top-K 结果
```

### 多模态警告机制

若 MinerU 返回了方案未覆盖的字段或降级处理，Pipeline 会：
1. 将警告信息记录到 SQLite `documents.warnings` 字段
2. 将文档状态置为 `needs_review`（而非 `failed`）
3. 前端文件管理页展示黄色 ⚠️ 警告卡片，告知用户具体警告内容

---

## 与需求文档的对照说明

| 需求 | 实现状态 | 备注 |
|------|----------|------|
| PDF / PPT / Word / 图片解析 | ✅ 已实现 | 通过 MinerU vlm 在线 API |
| 音视频转写 | ⏳ 暂未实现 | 作为提升项，基础链路完成后接入 |
| 自研 IR 中间格式 | ✅ 已实现 | `models_ir.py` + `adapters/` |
| DOM 重建与 header_path | ✅ 已实现 | `dom_builder.py` |
| Parent/Child 切片 | ✅ 已实现 | `chunkers/` |
| 多模态富化（图片/表格摘要） | ✅ 已实现 | `enrichers/`，qwen3.5-flash |
| Qdrant 向量索引 | ✅ 已实现 | text-embedding-v4 1024维 |
| SQLite FTS5 关键词索引 | ✅ 已实现 | `database.py` |
| 混合检索 + RRF | ✅ 已实现 | `retrieval_service.py` |
| qwen3-rerank 重排序 | ✅ 已实现 | `rerank_service.py` |
| qwen3.5-plus 流式问答 | ✅ 已实现 | `qa_service.py`，SSE |
| 多知识库空间管理 | ✅ 已实现 | `api/kb.py` |
| 文件上传 + 状态展示 | ✅ 已实现 | 前端文件管理页 |
| 对话问答 + 引用面板 | ✅ 已实现 | SSE 流式 + CitationPanel |
| PDF 原文预览 | ✅ 已实现 | origin-pdf API + react-pdf |
| 任务状态监控 | ✅ 已实现 | `TasksPage` + 自动刷新 |
| MinerU 解析警告提示 | ✅ 已实现 | 黄色 Alert + needs_review 状态 |
| 文件夹上传 / 批量操作 | ✅ 已实现 | `relative_path` + 前端全选批量删除/重解析 |
| bbox 高亮定位 | ✅ 已实现 | 检索链路透传 bbox，Chat 页预览时叠加高亮 |
| 目录树浏览与文件夹展开/收起 | ⏳ 暂未实现 | 当前按 `relative_path` 列表展示 |
| 文件夹删除 / 文件夹重命名 / 文件移动 | ⏳ 暂未实现 | 当前为文件级管理 |
| 按文件类型筛选 | ⏳ 暂未实现 | 需在文件管理页补筛选器 |
| 设置页在线配置 | ⏳ 暂未实现 | `SettingsPage` 仍为占位页面 |

---

## 开发说明

### 运行测试

```bash
cd backend

# Stage 2: MinerU 解析与 IR 标准化
uv run python test_stage2.py

# Stage 3: 切片与索引
uv run python test_stage3.py

# Stage 4: 检索与问答
uv run python test_stage4.py
```

### 清理运行时数据（重置为初始状态）

```bash
# Windows PowerShell
Remove-Item data\sqlite\* -Recurse -Force
Remove-Item data\qdrant_storage\* -Recurse -Force
Remove-Item data\uploads\* -Recurse -Force
Remove-Item data\mineru_zips\* -Recurse -Force
Remove-Item data\rag_output\* -Recurse -Force
```

---

## 致谢

- [MinerU](https://mineru.net) — 提供高质量文档解析服务
- [阿里云百炼](https://bailian.console.aliyun.com) — 提供向量化、重排序、VLM 与问答模型
- [Qdrant](https://qdrant.tech) — 高性能本地向量数据库
- [FastAPI](https://fastapi.tiangolo.com) / [React](https://react.dev) / [Tailwind CSS](https://tailwindcss.com)

---

*课程设计 · 程序设计实训 · 09班李宇 2022210347*
