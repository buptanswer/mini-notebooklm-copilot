# Release Notes

> Mini-NotebookLM · 面向大学生的多模态课程知识库与 AI 辅导系统

---

## v1.1.0（2026-05-21）

### 新增：MinerU 格式监控系统

新增独立的"严格审计"层，与归一化器的"宽容转换"策略互补，用于持续追踪 MinerU SaaS API 的输出格式变化：

- **`backend/app/adapters/format_checker.py`** — 格式偏差审计模块
  - 维护 `KNOWN_BLOCK_TYPES`、`BLOCK_KNOWN_FIELDS`、`CONTENT_KNOWN_FIELDS` 等完整格式规范常量
  - `check_bundle(zip_root, source_filename, doc_id) → FormatCheckReport` 主入口
  - `log_report_to_file(report, log_path)` — 追加到 `data/format_probe_log.jsonl`（仅有偏差时写入）
  - 偏差三级分类：`error` / `warning` / `info`

- **`backend/tools/mineru_format_probe.py`** — 独立探针 CLI 脚本
  - 离线模式（默认）：扫描 `data/mineru_zips/` 已解压目录
  - 在线模式（`--online`）：上传文件 → 调 MinerU API → 校验 ZIP
  - 彩色输出 + 聚合汇总，退出码：0=clean / 1=errors / 2=warnings / 3=info
  - 用法：`cd backend && uv run python tools/mineru_format_probe.py`

- **Pipeline 集成（步骤 [E+]）** — `pipeline_service.py`
  - 每次文档解析自动在 [E] 解压后、[F] 归一化前运行格式审计
  - 有偏差时追加 JSONL 日志，格式完全符合时记录 INFO 日志
  - 探针异常不影响后续解析流程

### 新增：MinerU 新块类型支持

| 新块类型 | 映射 | 说明 |
|----------|------|------|
| `chart` | `image`（AssetType=`chart_image`）| 图表块，含 image_source + Markdown 数据表格 |
| `index` | `list` | 目录/TOC 块，结构与 list 一致 |

涉及文件：`adapters/normalizer.py`、`models/models_raw_mineru.py`（新增 `RawChartContent`）、`models/models_ir.py`（`AssetType` 新增 `"chart_image"`）

### 新增：Office 原生解析支持（DOCX / PPTX）

MinerU 对 DOCX/PPTX 使用 Office 原生引擎，bbox 坐标键**缺失**（非 null）：

- `normalizer.py`：bbox 键不存在时静默使用 `[0,0,0,0]` 占位，不触发 degraded 警告
- `ir_validator.py`：`[0,0,0,0]` 为 Office 原生占位符，跳过坐标有效性校验
- `ChatPage.tsx`：`anchor_origin_pdf_path` 为空时（DOCX/PPTX 无 origin.pdf）隐藏"查看原文"按钮，改为提示"非 PDF 格式，不支持原文预览"

### 新增字段适配

`normalizer.py` 新增多项字段支持，修复 DOCX/PPTX 解析时大量 unknown_keys 警告：

- 块顶级：`anchor`（DOCX 标题锚点）、`sub_type`（图表子类型）
- `list.content`：`attribute`（`"unordered"` / `"ordered"`）
- `list_item`：`ilevel`（缩进层级）、`prefix`（项目符号）、`anchor`（TOC 锚点）
- `image.content.content`：VLM OCR 文本（纳入 embedding）
- `TextSegment`：`url`（超链接 URL）、`style`（Office 样式标记）

### 优化：QA 问答服务

- `qa_service.py` 新增 `_SYSTEM_PROMPT` 系统提示词（知识库问答专用）
- 消息结构从单条 user 改为 `[system, user]` 两条，引导模型更精准参考知识库内容
- 上下文格式优化：加入页码 + 章节路径元信息，提升引用定位准确性

### 文档更新

- `doc/09班李宇2022210347-本地ai知识库需求分析报告V7.md`：完整重写为项目现状交接文档（~600 行）
- `doc/MinerU to RAG Pipeline 架构设计与数据流方案.md`：更新 §3.1 ZIP 结构、§5.7 新块类型，新增 §15 实现更新记录
- `doc/在线API输出文件格式（SaaS推断版）.md`：新增 §9.5 `preproc_blocks` 字段说明，更新 §5.2.3、§5.2.4
- `README.md`：新增格式监控系统使用说明、目录结构更新

### 测试

```
后端 API 端到端测试：49/49 全部通过
TypeScript 编译检查：0 错误
前端生产构建：✓ 通过
格式探针（7 文档）：7/7 ✅ 退出码 0
```

---

## v1.0.0（2026-05-21）

### 版本说明

**v1.0.0** 是本项目的基础成品版本（Base Release）。

本版本完整实现了从文档上传到多模态问答的全链路 RAG 工作台，通过充分的代码审查与端到端测试（49/49 API 测试全部通过），确保所有核心功能稳定可用，可作为后续二次开发的基础。

---

### 核心功能

### 知识库管理
- 创建、查看、编辑、删除知识库
- 支持**通用**和**课程**两种类型（`kb_type`）
- 卡片式列表界面，显示文件数量和最后更新时间

### 文档管理
- 支持 PDF、PPT/PPTX、Word/DOCX、PNG/JPG 等格式上传
- 支持文件夹批量上传（保留相对路径）
- 批量选择、批量删除、批量重新解析
- 实时状态轮询（上传 → 解析中 → 已索引 / 需检视 / 失败）
- 文档状态：`uploaded` / `parsing` / `indexed` / `needs_review` / `failed`

### 文档解析流水线（16 步）
1. 申请 MinerU 预签名上传 URL
2. PUT 上传文件到 MinerU
3. 轮询 MinerU 批处理结果
4. 下载解析结果 ZIP
5. 解压 + bundle 识别
6. 归一化为自研 IR（中间表示）格式
7. DOM 重建（section 树 + header_path）
8. 脚注关联
9. 读取 layout.json 元数据
10. 写出 document_ir.json
11. 构建 ParentChunk（结构感知）
12. 构建 ChildChunk（150-250 token）
13. 向量化（text-embedding-v4，1024 维）
14. 写入 Qdrant + SQLite 索引
15. 写出 parent/child chunks JSONL
16. 更新文档状态

### 混合检索问答
- 混合检索：向量搜索（Qdrant cosine）+ 关键词检索（SQLite FTS5 BM25）+ RRF 融合（k=60）
- 重排序：qwen3-rerank
- 流式回答：SSE 逐 token 推送
- 引用来源展示：引用编号 + 页码 + 章节路径
- PDF 原文预览：内嵌 PDF 查看器 + bbox 高亮定位
- 支持多 Provider：DashScope / DeepSeek / DeepSeek-R1 / OpenAI / Moonshot 等

### 任务监控
- 实时任务列表（自动轮询，5 秒刷新）
- 显示任务 ID、文档 ID、类型、状态、进度百分比、错误信息、时间戳

### 设置页面
- 后端服务实时健康检查
- API Key 配置说明（含环境变量名、用途、申请链接）
- 当前模型配置展示
- 数据目录路径说明
- Swagger UI / ReDoc 快速链接

---

### 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + aiosqlite + Qdrant（本地文件模式） |
| 前端框架 | React 19 + Vite 7 + Tailwind CSS v4 + Shadcn 风格组件 |
| 文档解析 | MinerU SaaS API（vlm 精准模式） |
| 向量化 | 阿里云百炼 text-embedding-v4（1024 维） |
| 重排序 | 阿里云百炼 qwen3-rerank |
| 问答生成 | qwen-plus（默认，可切换任意 OpenAI 兼容 Provider） |
| 向量库 | Qdrant（本地持久化，无需 Docker） |
| 关系数据库 | SQLite（WAL 模式 + FTS5 全文索引） |
| PDF 预览 | react-pdf + pdfjs-dist |
| 包管理 | Python: uv · Node: npm |

---

### 本次发布修复（对比初始草稿版本）

| 类别 | 问题 | 修复 |
|------|------|------|
| 前端 Bug | `ChatPage` 高度计算错误（`h-[calc(100vh-4rem)]`，Layout 用侧边栏不是顶栏） | 改为 `h-full` |
| 前端 Bug | Markdown 渲染无样式（`@tailwindcss/typography` 未安装，`prose` 类无效，Tailwind preflight 重置了列表样式） | 添加自定义 `.md-prose` CSS 样式，覆盖列表、标题、代码块、表格等 |
| 前端 Bug | 文件页面标题显示原始 UUID | 页面头部现在显示知识库名称和描述 |
| 前端 Bug | 设置页面为空占位符 | 完整实现：服务状态、API 配置、模型配置、数据目录 |
| 前端 Bug | `TaskStatus` 类型含后端从未使用的 `"pending"` | 移除，改为 `"created" \| "running" \| "done" \| "failed"` |
| 前端 Bug | 未知路由无处理 | 添加 `*` → `/` 重定向 |
| 后端 Bug | `tasks` 表 DDL `DEFAULT 'pending'`，但代码实际写入 `'created'` | 统一改为 `DEFAULT 'created'` |
| 后端 Bug | MinerU SaaS API 更新了 ZIP 输出格式：`content_list_v2.json` 现以 `{uuid}_content_list_v2.json` 命名，origin 文件扩展名跟随原始文件（`.docx`/`.pptx` 等，不再固定为 `.pdf`），导致所有文档解析失败 | `bundle_parser.py` 更新匹配规则，同时兼容固定名和 UUID 前缀两种格式；仅在 origin 文件为 `.pdf` 时才启用 PDF 预览功能 |
| 依赖问题 | `@tailwindcss/oxide` 原生绑定损坏（npm 已知 Bug） | 删除 `node_modules` 和 `package-lock.json` 后重装 |

---

### 测试

```
后端 API 端到端测试：49/49 全部通过（无需外部 API Key）
TypeScript 编译检查：0 错误
前端生产构建：✓ 通过
```

**运行测试：**
```powershell
cd backend
uv run python test_api.py
```

---

### 快速启动

**前置要求：**
- Python ≥ 3.11（推荐通过 uv 管理）
- Node.js ≥ 20
- MinerU API Key（[申请地址](https://mineru.net)）
- 阿里云百炼 API Key（[申请地址](https://bailian.console.aliyun.com)）

**后端：**
```powershell
cd backend
cp .env.example .env   # 填入 API Key
uv sync
uv run uvicorn app.main:app --reload
```

**前端：**
```powershell
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`

---

### 已知限制

- MinerU 在线 API 有文件大小限制（单文件建议 ≤ 100MB）
- 解析速度取决于 MinerU 服务响应时间（一般 30 秒 ~ 数分钟）
- Qdrant 退出时打印一行 `ImportError: sys.meta_path is None` 警告，这是 Qdrant Python 客户端的已知问题，不影响功能

---

### 后续开发计划（v1.1+）

- **MinerU 格式监控系统** — 严格格式审计 + 探针脚本（已在 v1.1.0 完成）
- **MinerU 新块类型适配** — chart/index 块 + Office 原生解析（已在 v1.1.0 完成）
- **模块七：AI 伴学·课后复盘** — 对话式复习笔记生成
- **模块八：AI 考官·期末冲刺** — 智能出题与答卷批改
- **模块九：AI 管家·日程防呆** — 课程信息提取与提醒

---

## 后续开发计划（v1.2+）

- **模块七：AI 伴学·课后复盘** — 数据库已就绪（`review_notes` 表），待实现后端 API + 前端页面
- **模块八：AI 考官·期末冲刺** — 数据库已就绪（`exam_questions`/`exam_papers`/`exam_submissions` 表），待实现完整出题-作答-批改流程
- **模块九：AI 管家·日程防呆** — 数据库已就绪（`course_info_cards` 表），待实现课程信息提取与日程提醒
- **FTS5 中文优化** — 引入 jieba 分词器提升中文关键词检索精度
- **音视频转写** — 集成录音/视频转文字后入库
