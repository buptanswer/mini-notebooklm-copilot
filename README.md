# Mini-NotebookLM

> 面向大学生的多模态课程知识库与 AI 辅导系统
>
> 课程设计项目 · 09班李宇 2022210347

---

## 项目简介

Mini-NotebookLM 是一款运行在本地 Windows 环境的 **知识库工作台**。用户可以把课程 PDF、PPT、Word 等文档上传到独立的知识库空间，由 MinerU 在线 API 解析后，经过自研的 IR 中间格式标准化、结构感知切片与向量索引，最终通过混合检索 + 重排序 + 多模态大模型实现高质量的文档问答。

核心工程主线：

```
原始文档 → MinerU 解析 → IR 标准化 → Parent/Child 切片 → 向量 + 关键词索引 → 混合检索 → 重排序 → 多模态问答
```

---

## 功能概览

### 已实现

| 功能 | 说明 |
|------|------|
| 多知识库空间管理 | 创建、查看、更新、删除知识库；支持「通用」和「课程」两种类型 |
| 文件夹绑定与自动同步 | 课程 KB 可绑定本地目录，点同步自动注册文件；支持 `text_only`（txt/md）和 `missing` 状态 |
| 多格式文档上传 | 支持 PDF、PPT/PPTX、Word/DOCX、图片（PNG/JPG）、TXT、MD |
| MinerU 异步解析 | 调用 MinerU 在线 API（vlm 精准模式），下载 zip，解析 content_list_v2.json + layout.json |
| 自研 IR 标准化 | DOM 重建、header_path 注入、多模态块建模、坐标锚点保留 |
| 结构感知切片 | Parent/Child 双层切片，不跨标题边界，list/code 保留原子性 |
| 多模态富化 | 图片/表格调用 VLM（默认 qwen-vl-plus）生成描述/摘要，用于检索增强 |
| 混合向量索引 | text-embedding-v4（1024维）向量存入 Qdrant；SQLite FTS5 关键词索引 |
| 混合检索 + RRF | 向量召回 + BM25 关键词召回并行，Reciprocal Rank Fusion 融合排序 |
| 重排序 | qwen3-rerank 对候选结果二次打分 |
| 多轮会话系统 | conversations + messages 持久化；支持 Fork 分支；SSE 流式问答；思维链开关 |
| 流式多模态问答 | 支持多 Provider（默认 qwen-plus/DashScope，可切换 DeepSeek、OpenAI 等）；SSE 流式输出 |
| 引用溯源 | 每条回答携带引用列表（文档、章节、页码、相关性分数） |
| PDF 原文预览 + bbox 高亮 | 引用面板「查看原文」，使用 react-pdf 定位页码并叠加 bbox 高亮框 |
| 文件夹上传 | 支持上传整目录，保留 relative_path 逻辑路径 |
| 批量操作 | 支持全选后批量删除、批量重解析 |
| 任务状态监控 | 实时查看解析/索引任务状态、进度与错误信息 |
| MinerU 警告提示 | 若 MinerU 返回异常字段或降级，前端黄色警告提醒用户复查 |
| 模块七：AI 伴学·课后复习 | 按日期+节次流式生成讲义，保存到磁盘，支持多轮追问和 Fork 分支 |
| 模块九：AI 管家·课程信息 | 自动提取课程名称、老师联系方式、考核方式、截止日期；多轮问答；deadline banner |
| 提示词管理 | 提示词文件化（`app/prompts/*.md`），支持热更新无需重启 |
| 设置页 | 展示 API 配置说明、当前模型信息、服务健康状态及链接 |

### 暂未实现（提升项）

- 音视频转写（飞书妙记 / 通义听悟）
- 目录树浏览与文件夹展开/收起
- 文件夹删除 / 重命名 / 文件移动
- 按文件类型筛选
- 模块八：AI 考官·期末冲刺（智能出题与答卷批改）
- FTS5 中文分词优化（jieba）

---

## 技术栈

### 后端

| 组件 | 选型 | 说明 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | 异步 API 服务 |
| 数据校验 | Pydantic v2 | Schema First，贯穿 IR / Chunk 全流程 |
| 向量数据库 | Qdrant（本地文件模式） | 存储 Child Chunk 向量，无需 Docker |
| 关系数据库 | SQLite + FTS5 | 文档元数据、任务状态、Parent/Child 映射、关键词索引 |
| 文档解析 | MinerU 在线 API（vlm） | PDF/PPT/Word/图片 → content_list_v2.json + layout.json |
| 向量模型 | text-embedding-v4（阿里云百炼） | 1024维，纯文本嵌入 |
| 重排序 | qwen3-rerank（阿里云百炼） | 候选 chunk 二次打分 |
| 视觉模型 | qwen-vl-plus（阿里云百炼，可配置） | 图片描述 / 表格摘要 |
| 问答模型 | 多 Provider 可切换（默认 qwen-plus/DashScope） | 最终问答，SSE 流式输出 |
| HTTP 客户端 | httpx | 与 MinerU / DashScope API 通信 |
| 包管理 | uv | 替代 pip，速度更快 |

### 前端

| 组件 | 选型 |
|------|------|
| 框架 | React 19 + Vite |
| 样式 | Tailwind CSS v4 |
| 路由 | React Router v7 |
| Markdown 渲染 | react-markdown + remark-gfm |
| 图标 | lucide-react |
| PDF 预览 | react-pdf |
| SSE 流式 | fetch + ReadableStream（非 EventSource） |

---

## 目录结构

```
mini-notebooklm/
├── backend/
│   ├── app/
│   │   ├── adapters/          # MinerU zip 解析与 IR 标准化层
│   │   │   ├── bundle_parser.py   # 解压 zip，提取 content_list_v2.json / layout.json / images
│   │   │   ├── dom_builder.py     # DOM 树重建，注入 header_path
│   │   │   ├── normalizer.py      # Raw MinerU → 标准 IR Block（宽松容错）
│   │   │   ├── footnote_linker.py # 脚注关联
│   │   │   └── format_checker.py  # MinerU 输出格式严格审计（与 normalizer 互补）
│   │   ├── api/               # FastAPI 路由
│   │   │   ├── kb.py              # 知识库 CRUD（含 PATCH 更新、级联删除场景数据）
│   │   │   ├── documents.py       # 文件上传、解析触发、删除、origin-pdf、raw-text
│   │   │   ├── chat.py            # 流式问答（SSE）、检索
│   │   │   ├── conversations.py   # 多轮会话 CRUD + 流式发送 + Fork
│   │   │   ├── course_info.py     # 模块九：课程信息卡片生成与问答
│   │   │   ├── review.py          # 模块七：课后复习讲义生成与追问
│   │   │   ├── settings.py        # 提示词管理端点
│   │   │   ├── tasks.py           # 任务状态查询
│   │   │   └── health.py          # 健康检查
│   │   ├── chunkers/          # Parent / Child 切片
│   │   │   ├── parent_chunker.py
│   │   │   └── child_chunker.py
│   │   ├── db/                # 数据库初始化与客户端
│   │   │   ├── database.py        # SQLite 建表、FTS5、懒迁移；含场景模块表
│   │   │   └── qdrant_client.py   # Qdrant 集合初始化
│   │   ├── enrichers/         # 多模态富化（图片描述 / 表格摘要）
│   │   ├── models/            # Pydantic 模型
│   │   │   ├── models_raw_mineru.py   # MinerU 原始输出 Schema
│   │   │   ├── models_ir.py           # 自研 IR 中间格式 Schema
│   │   │   └── models_chunk.py        # Parent / Child Chunk Schema
│   │   ├── prompts/           # 提示词文件（Markdown，支持热更新）
│   │   │   ├── qa_system.md           # 知识库问答系统提示词
│   │   │   ├── course_info_extract.md # 课程信息结构化抽取提示词
│   │   │   ├── review_first.md        # 讲义生成-首节提示词
│   │   │   ├── review_subsequent.md   # 讲义生成-后续节提示词
│   │   │   └── course_info_chat.md    # 课程信息问答系统提示词
│   │   ├── services/          # 业务服务
│   │   │   ├── pipeline_service.py    # 全流程编排（上传→解析→IR→切片→索引）
│   │   │   ├── mineru_client.py       # MinerU API 客户端（v4 批量精准解析）
│   │   │   ├── embedding_service.py   # text-embedding-v4 向量化
│   │   │   ├── index_service.py       # Qdrant + SQLite FTS5 入库
│   │   │   ├── retrieval_service.py   # 混合检索 + RRF 融合
│   │   │   ├── rerank_service.py      # qwen3-rerank 重排序
│   │   │   ├── qa_service.py          # 多 Provider 流式问答 + stream_llm_completion
│   │   │   ├── folder_sync_service.py # 文件夹绑定扫描同步
│   │   │   ├── conversation_service.py# 多轮会话 CRUD + Fork + 流式补全
│   │   │   ├── course_info_service.py # 模块九：课程信息提取与截止日期解析
│   │   │   └── lecture_review_service.py # 模块七：课后讲义生成与保存
│   │   ├── validators/        # IR / Chunk 结构校验
│   │   ├── writers/           # IR / Chunk JSONL 落盘
│   │   ├── config.py          # 全局配置（pydantic-settings，多 Provider 支持）
│   │   └── main.py            # FastAPI 应用入口
│   ├── tools/                 # 运维工具脚本
│   │   └── mineru_format_probe.py # MinerU 格式探针（离线/在线两种模式）
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .env.example           # 环境变量配置模板
│   ├── test_api.py            # HTTP API 端到端测试（无需外部 API）
│   ├── test_stage2.py         # MinerU 解析与 IR 集成测试
│   ├── test_stage3.py         # 切片与索引集成测试
│   └── test_stage4.py         # 混合检索与问答端到端测试
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts          # 所有后端 API 调用封装
│   │   │   └── types.ts           # TypeScript 接口定义
│   │   ├── components/
│   │   │   ├── Layout.tsx         # 左侧主导航布局（可折叠）
│   │   │   └── ui/                # 基础 UI 组件（Button、Badge、Dialog 等）
│   │   ├── components/
│   │   │   ├── KBLayout.tsx           # 知识库二级布局（二级侧边栏 + deadline banner）
│   │   │   ├── Layout.tsx             # 左侧主导航布局（可折叠）
│   │   │   └── ui/                    # 基础 UI 组件
│   │   ├── pages/
│   │   │   ├── KnowledgeBasePage.tsx  # 知识库首页（卡片网格，含类型选择 + 文件夹绑定）
│   │   │   ├── KBFilesPage.tsx        # 文件管理页（上传 / 批量操作 / 同步按钮）
│   │   │   ├── ChatPage.tsx           # 对话问答页（SSE + 引用面板 + PDF bbox 高亮）
│   │   │   ├── ReviewPage.tsx         # 模块七：课后复习（日期选择 + 流式生成 + 追问）
│   │   │   ├── CourseInfoPage.tsx     # 模块九：课程管家（信息卡片 + deadline + 问答）
│   │   │   ├── TasksPage.tsx          # 任务监控页
│   │   │   └── SettingsPage.tsx       # 设置页（配置说明 / 服务状态）
│   │   ├── lib/utils.ts
│   │   ├── index.css
│   │   ├── App.tsx                # 路由配置（含 KBLayout 嵌套路由）
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── data/                      # 运行时数据（不纳入版本控制）
│   ├── sqlite/                # SQLite 数据库
│   ├── qdrant_storage/        # Qdrant 向量存储
│   ├── uploads/               # 原始上传文件
│   ├── mineru_zips/           # MinerU 返回压缩包
│   ├── rag_output/            # IR JSON / Chunk JSONL / 图片
│   └── format_probe_log.jsonl # MinerU 格式变更审计日志（有偏差时自动写入）
│
├── doc/                       # 项目文档
└── test_inputs/               # 测试用样本文件
```

---

## 快速开始

### 前置依赖

- Python 3.11+（建议 3.12）
- Node.js 20+（v20.x 或 v22.x）
- [uv](https://docs.astral.sh/uv/) 包管理器
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
# 编辑 .env，填写以下必填项：
#   MINERU_API_KEY=your_mineru_key
#   ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_dashscope_key
```

### 3. 启动后端

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端启动后会自动创建 `data/` 下所有目录、初始化 SQLite 数据库（含所有表）和 Qdrant 向量集合。

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

1. **新建知识库**：在首页点击「新建知识库」，选择类型（通用 / 课程）并填写名称
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
| `纯文本` | txt/md 文件，无需解析，可直接供模块七使用 |
| `文件缺失` | 文件夹同步时检测到原文件已从磁盘删除 |
| `失败` | 解析或入库失败，可点击重新解析 |

---

## API 文档

后端服务启动后，访问 `http://127.0.0.1:8000/docs` 查看自动生成的 Swagger UI。

### 主要端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/kb` | 列出所有知识库 |
| `POST` | `/api/kb` | 创建知识库（支持 `kb_type: "general"\|"course"`） |
| `GET` | `/api/kb/{kb_id}` | 获取单个知识库详情 |
| `PATCH` | `/api/kb/{kb_id}` | 更新知识库名称 / 描述 / 类型 |
| `DELETE` | `/api/kb/{kb_id}` | 删除知识库（级联删除所有文档、向量和场景数据） |
| `GET` | `/api/documents/{kb_id}` | 列出知识库内文档 |
| `POST` | `/api/documents/{kb_id}/upload` | 上传文件（支持 `relative_path` 逻辑路径） |
| `GET` | `/api/documents/{kb_id}/{doc_id}` | 获取文档详情（含 status，可用于轮询） |
| `POST` | `/api/documents/{kb_id}/{doc_id}/parse` | 触发解析（支持重新解析） |
| `DELETE` | `/api/documents/{kb_id}/{doc_id}` | 删除文档（含向量和文件） |
| `GET` | `/api/documents/{kb_id}/{doc_id}/origin-pdf` | 获取 origin.pdf 原文 |
| `POST` | `/api/chat/{kb_id}` | 流式问答（SSE，`text/event-stream`） |
| `POST` | `/api/chat/{kb_id}/search` | 纯检索（不生成回答，供调试） |
| `POST` | `/api/kb/{kb_id}/sync-folder` | 扫描绑定文件夹并同步文件状态 |
| `GET` | `/api/documents/{kb_id}/{doc_id}/raw-text` | 获取 txt/md 文件纯文本内容 |
| `POST` | `/api/conversations` | 创建多轮会话 |
| `GET` | `/api/conversations` | 列出会话（按 kb_id/scenario 筛选） |
| `POST` | `/api/conversations/{id}/send` | 发送消息并获取流式回复（SSE） |
| `POST` | `/api/conversations/{id}/fork` | Fork 会话（从指定消息截断历史） |
| `POST` | `/api/course-info/{kb_id}/generate` | 生成课程信息卡片 |
| `GET` | `/api/course-info/{kb_id}` | 获取课程信息卡片 |
| `POST` | `/api/course-info/{kb_id}/chat` | 课程信息多轮问答（SSE） |
| `GET` | `/api/review/{kb_id}/dates` | 列出可复习日期 |
| `POST` | `/api/review/{kb_id}/generate` | 流式生成课后讲义（SSE，按节次分段） |
| `POST` | `/api/review/{kb_id}/save-notes` | 保存讲义到磁盘并触发同步 |
| `GET` | `/api/review/{kb_id}/notes` | 读取指定日期的已保存讲义（`?date=YYMMDD`） |
| `GET` | `/api/tasks` | 列出最近任务（默认 50 条） |
| `GET` | `/api/tasks/doc/{doc_id}` | 列出指定文档的任务 |
| `GET` | `/api/tasks/{task_id}` | 获取单个任务详情 |

---

## 环境变量说明

完整说明见 `backend/.env.example`。核心配置：

```env
# MinerU 在线 API（必填）
MINERU_API_KEY=your_mineru_key

# 阿里云百炼 DashScope（必填，用于嵌入/重排序/VLM）
ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_dashscope_key

# QA 问答模型（可选，不填则自动使用 DashScope qwen-plus）
# 切换到 DeepSeek 示例：
# QA_BASE_URL=https://api.deepseek.com/v1
# QA_API_KEY=sk-xxxxxxxx
# QA_MODEL=deepseek-chat
```

### 多 Provider QA 支持

问答模型支持通过环境变量切换到任意 OpenAI 兼容 Provider：

| Provider | QA_BASE_URL | QA_MODEL |
|----------|------------|---------|
| 阿里云百炼（默认） | 不填 | 不填（默认 qwen-plus） |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| DeepSeek 思维链 | `https://api.deepseek.com/v1` | `deepseek-reasoner` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| 月之暗面 | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |

---

## 核心设计说明

### 知识库类型（kb_type）

创建知识库时可选择两种类型：
- **通用（general）**：适合笔记、资料整理与问答
- **课程（course）**：面向课程学习，支持绑定本地文件夹、文件夹自动同步；开启模块七（课后复习）与模块九（课程管家）功能

### IR 中间格式

系统不直接将 MinerU 原始输出送入向量库，而是经过自研 IR 标准化层处理：

1. `bundle_parser.py` 解压 MinerU zip，提取 `content_list_v2.json`、`layout.json`、`*_origin.pdf`、`images/`
2. `normalizer.py` 将 MinerU Raw Block 转为标准 `IRBlock`（统一字段名，类型归一化）
3. `dom_builder.py` 重建文档 DOM 树，为每个块注入 `header_path`（标题路径链）
4. 输出 `document_ir.json` + `document_ir_enriched.json` 落盘，供切片层使用

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
└──  RRF 融合 → qwen3-rerank 重排序 → Top-K 结果 → 流式问答
```

### 多模态警告机制

若 MinerU 返回了方案未覆盖的字段或降级处理，Pipeline 会：
1. 将警告信息记录到 SQLite `documents.warnings` 字段
2. 将文档状态置为 `needs_review`（而非 `failed`）
3. 前端文件管理页展示黄色 ⚠️ 警告卡片，告知用户具体警告内容

### MinerU 格式监控系统

每次文档解析后自动运行严格格式审计（步骤 [E+]），检测 MinerU API 输出格式是否发生变化：

```bash
cd backend

# 离线检查已有解析结果（不消耗 API 配额）
uv run python tools/mineru_format_probe.py

# 实时上传测试文件检查（消耗 MinerU API 配额）
uv run python tools/mineru_format_probe.py --online
```

退出码：`0`=格式完全符合，`1`=有错误，`2`=有警告，`3`=仅提示（可接入 CI）

格式变更日志自动追加到 `data/format_probe_log.jsonl`。

---

## 测试

```bash
cd backend

# API 端到端回归测试（不依赖外部 API，快速）
uv run python test_api.py        # 49 个测试

# v1.2.0 新功能集成测试（不依赖外部 API，快速）
uv run python test_v120.py       # 85 个测试
# 注意：运行前需确保 uvicorn 服务未启动（Qdrant 文件锁限制单进程访问）

# Stage 2: MinerU 解析与 IR 标准化（需要 MINERU_API_KEY）
uv run python test_stage2.py

# Stage 3: 切片与索引（需要 ALIBABA_CLOUD_ACCESS_KEY_SECRET）
uv run python test_stage3.py

# Stage 4: 混合检索与问答（需要全部 API Key）
uv run python test_stage4.py
```

---

## 清理运行时数据

```powershell
# Windows PowerShell — 清空数据库与缓存，重置为初始状态
# 注：保留各目录下的 .gitkeep 文件，不影响目录结构

# 删除 SQLite 数据库文件
Remove-Item data\sqlite\mini_notebooklm.db -Force -ErrorAction SilentlyContinue

# 清理向量存储、上传文件、解析缓存（保留 .gitkeep）
foreach ($sub in @('qdrant_storage', 'uploads', 'mineru_zips', 'rag_output')) {
    Get-ChildItem "data\$sub" -Recurse |
        Where-Object { -not $_.PSIsContainer -and $_.Name -ne '.gitkeep' } |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem "data\$sub" -Recurse -Directory |
        Sort-Object FullName -Descending |
        Remove-Item -ErrorAction SilentlyContinue
}
```

清理后重启后端，SQLite 数据库和向量索引会自动重新初始化。

---

## 致谢

- [MinerU](https://mineru.net) — 提供高质量文档解析服务
- [阿里云百炼](https://bailian.console.aliyun.com) — 提供向量化、重排序、VLM 与问答模型
- [Qdrant](https://qdrant.tech) — 高性能本地向量数据库
- [FastAPI](https://fastapi.tiangolo.com) / [React](https://react.dev) / [Tailwind CSS](https://tailwindcss.com)

---

*课程设计 · 程序设计实训 · 09班李宇 2022210347*
