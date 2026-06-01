# Release Notes

> Mini-NotebookLM · 面向大学生的多模态课程知识库与 AI 辅导系统

---

## v1.3.0（2026-05-31 开发 · 2026-06-01 验收定稿）— 统一对话架构 + 大厂级阅读器前端重构

针对 v1.2.0 验收暴露的对话体系割裂与 UI 通用感问题，做前后端协同重构。**已通过用户验收。**

### 后端：统一对话核心
- 新增**单一流式原语 `conversation_service.stream_turn`** + **单一 SSE 词汇**（`conversation / message_start / citations / thinking / delta / message_end / done / error`），取代此前 3 套互不相同的实现。
- 模块七讲义生成（`lecture_review_service`）重写为按节调用 `stream_turn`（录音作 hidden user message，section 元数据打到 assistant），与追问、模块九、通用对话共用同一条流式路径与渲染。
- 通用对话迁移到会话（`scenario="general"` + `rag_mode`），从此**有历史、可 fork、可重载**；引用持久化到 assistant message。
- **Fork 通用化**：任意会话的任意 assistant 消息均可分叉（统一回传 `message_id`）。

### 后端：讲义索引（问题 3）
- 新增 `text_index_service`：Markdown 感知切片（**标题分 Parent + 空行分段 + 句窗滑动**，非整段索引）→ 嵌入 → 写 Qdrant + FTS。生成的「课堂要点.md」**保存时自动索引**；新增 `POST /api/documents/{kb}/{doc}/index-text` 手动索引端点。
- **录音转写 .txt 永不进 RAG 索引**（仅作模块七生成素材，避免原始噪声污染问答检索）。

### 后端：热修——切片死循环导致后端冻结
- `child_chunker._build_windows` 旧实现用 `while i < len(sentences)` 推进，遇到「单句长度落在 `(max−overlap, max]` 区间」时 flush 后会反复重试同一句、永不前进，**陷入死循环并冻结整个 asyncio 事件循环**（验收时点击讲义索引后整个后端卡死、前端全部「加载中 / failed to fetch」即由此引起）。
- 改为 `for sent in sentences` 逐句消费 + 超长句硬切（`len(sent) > max_chars` 先切段），flush 后 `current = [overlap_text, sent]` 直接消费当前句、不再回退重试。新增 `_test_chunk_windows` 用 480 字「杀手句」回归，确保必然终止。

### 后端：批量解析稳定性（问题 1）
- 新增全局解析并发上限（`MAX_CONCURRENT_PARSES`，默认 2），批量重解析不再 N 路齐发打爆 MinerU/OSS/DashScope 连接。
- 抽出共享瞬时重试 `services/http_retry.py`，应用到 MinerU + DashScope（嵌入/重排/VLM）调用。

### 前端：「研读室」设计系统 + 体验修复
- 全新设计语言：暖纸阅读器质感 + 精致 AI 动效；**浅色 / 暗色 / 护眼(sepia) 三主题**（长时间复习护眼）；Fraunces × Hanken Grotesk 字体；terracotta 主调；纸纹质感；`motion` 动效（流式光标、思维链 shimmer、入场动画，尊重 reduced-motion）。
- **统一 `ChatThread` + `useConversation` + 单一 SSE 解析器**（替代原 5 个重复 stream 函数），所有对话页复用。
- 修复 v1.2.0 验收问题：
  - 生成讲义时**思维链展开不再自动收起**（改函数式 state，不再被流式事件整体覆盖）；
  - 重新打开历史对话**讲义不再被追问消息覆盖、追问区不再空白**（线程化重载，不再手搓 sectionNotes）；
  - **课后追问可 fork**（任意消息均可）。
- 全部页面与外壳（书架首页 / 文件 / 阅读·对话 / 课后复习 / 课程管家 / 任务 / 设置 / 二级侧边栏 + DDL banner）在新系统上重做。

### 验证
- 后端 `test_v120.py` **105/105 通过**（含统一词汇、讲义多 section、任意消息 fork、讲义 .md 自动索引、录音 .txt 不索引、index-text 拒绝录音、`_test_chunk_windows` 切片死循环回归等）；`basedpyright` standard **0 错误**。
- 前端 `tsc -p tsconfig.app.json`（项目本地 5.9.3）**0 错误**、`eslint` **0 错误**（11 warnings）、生产构建通过；真机渲染经 playwright 验证（首页 / 复习页 / 三主题切换，0 控制台报错）。

---

## 文档体系重构（2026-05-31，仅文档，不涉代码）

v1.2.0 通过用户验收后重构 `doc/`，并在 v1.3.0 开发中进一步收敛为「稳定快照（`项目当前情况.md`）+ 实时进度（`progress.md`）」双文档模型：

- `09班李宇2022210347-本地ai知识库需求分析报告V7.md` → **`项目当前情况.md`**（改写为与代码一致的交接文档）
- 原计划保留的 `下一步开发目标.md` / `开发实施手册.md` 两篇规划文档，**在 v1.3.0 中并入项目根目录 `progress.md`**（实时计划 + 进度 + 自上版改动记录），并据此把「写 progress.md」固化为长任务的全局约定；两篇原文如需查阅可从 v1.2.0 git 历史找回。
- 新建 `doc/mineru/`，收纳官网下载文档：`MinerU API 文档（新的）.md`（新版 API 文档）、`输出文件格式（新的）.md`（官网声称格式，更新滞后有误，仅供参考）
- 删除 `mineru API文档（格式化）.md`（官网旧 API 文档）与 `03课：MinerU 在线 API 实战教程 - 文档.md`（与新 API 文档重叠，且其 SDK/CLI/MCP/飞书等内容本项目不用）
- 移除空目录 `doc/新文档/`；新增 `doc/文档导览.md` 导览

go-forward 维护约定：进行中长任务随时更新 `progress.md`；每轮开发后更新 `项目当前情况.md` + README + RELEASE_NOTES；MinerU 字段变化更新《在线API输出文件格式（SaaS推断版）》；解析入库工作流变化更新《MinerU to RAG Pipeline 架构设计与数据流方案》。

---

## v1.2.0（2026-05-22）

### 新增：文件夹绑定与自动同步

课程知识库支持绑定本地文件夹，按约定目录结构自动注册文件：

- `POST /api/kb/{kb_id}/sync-folder` — 扫描绑定目录，新文件自动入库（txt/md 直接标记 `text_only`，其他格式标记 `uploaded` 等待解析）
- 文件消失时状态自动更新为 `missing`，重新出现后恢复
- `folder_category` 自动按目录名映射（课堂录音、课件、作业、通知）
- `GET /api/documents/{kb_id}/{doc_id}/raw-text` — 读取 txt/md 文件纯文本（模块七使用）

### 新增：多轮会话系统

- `conversations` + `messages` 表持久化，支持无限轮次
- Fork 语义：从任意消息截断历史创建新分支，原会话不变
- SSE 流式发送端点 `POST /api/conversations/{id}/send`
- 支持 `enable_thinking` 开关（思维链输出）和 `metadata` 扩展字段

### 新增：模块九 — AI 管家（课程信息卡片）

- 5 路混合检索 → LLM JSON 结构化抽取 → 课程信息卡片
- 自动解析截止日期（ISO / 中文月日 / 斜杠格式），计算 `days_left`
- KB 顶部 deadline banner（7 天内到期任务）
- 课程信息多轮问答（`POST /api/course-info/{kb_id}/chat`，SSE）

### 新增：模块七 — AI 伴学（课后复习讲义生成）

- 按日期 + 节次扫描录音转写文件，一次性流式生成全部节次讲义
- 每节独立 SSE 段落（`section_start`/`thinking`/`delta`/`section_done`），前端按节分组展示
- 讲义保存到磁盘，经文件夹同步自动登记为 `text_only` 文档
- 支持追问（在同一 conversation 中继续多轮对话）
- 支持 Fork 分支复习

### 新增：提示词管理

- 提示词独立为 `backend/app/prompts/*.md` 文件，热更新无需重启
- `GET /api/settings/prompts` 查看已加载提示词列表
- `POST /api/settings/prompts/reload` 立即重载

### 新增：前端嵌套路由与二级侧边栏

- `KBLayout` 作为知识库二级布局，包含返回按钮、KB 名称、类型标识
- 课程 KB 显示额外导航项：课后复习、课程管家
- deadline banner：临近截止日期时在顶部显示橙色提示条

### 文档状态扩展

| 新状态 | 含义 |
|--------|------|
| `text_only` | txt/md 文件，无需 MinerU 解析，可直接供模块七使用 |
| `missing` | 文件夹同步时原文件已从磁盘删除 |

### Bug 修复（本版本自检）

| 位置 | 问题 | 修复 |
|------|------|------|
| `kb.py` DELETE | 删除有多轮会话记录的 KB 时报 `FOREIGN KEY constraint failed` | 级联删除 `messages` → `conversations` 再删 KB |
| `qa_service.py` | `stream_answer` 重构后遗留 `payload/headers/url` 死代码（从未被使用） | 删除死代码 |
| `course_info_service.py` | LLM 返回无效 JSON 时静默失败，无日志 | 添加 `logger.warning` 记录原始响应片段 |
| `types.ts` | `ReviewNote` 接口未定义，前端无法使用加载讲义功能 | 补充 `ReviewNote` 接口定义 |
| `client.ts` | `loadReviewNotes` 函数缺失（后端端点存在但前端未封装） | 添加 `loadReviewNotes(kbId, date)` |
| `ReviewPage.tsx` | 历史会话侧边栏点击仅更新状态，未触发 URL 路由，导致讲义不加载 | 改为 `navigate(...)` 触发 `useEffect` URL 监听 |
| `ReviewPage.tsx` | 缺少「加载已存盘讲义」按钮（`has_notes=true` 时无法查看已保存内容） | 添加按钮，调用 `loadReviewNotes` 填充视图 |
| `ReviewPage.tsx` | 缺少「导出 PDF」按钮 | 添加 `window.print()` 按钮 |

### 第二轮验收修复（2026-05-23）

| 位置 | 问题 | 修复 |
|------|------|------|
| `mineru_client.py` | MinerU API 偶发网络失败直接报错 | `_retry` 指数退避重试（3 次，2s→4s→8s），仅对瞬时网络故障重试，耗尽后报清晰错误 |
| `KBFilesPage.tsx` | 文件列表是扁平列表，不直观 | 改为按 `relative_path` 分层的树形目录视图（可折叠）+ Shift 范围多选 |
| `ChatPage.tsx` / `CourseInfoPage.tsx` | 对话界面缺少 Fork、历史会话功能 | 每条助手消息支持 Fork；历史会话切换；ChatPage 改用对话 API（持久化以支持 Fork） |
| `ReviewPage.tsx` 等 | Markdown 未渲染、思维链流式中折叠、切换日期残留状态 | 统一改用 ReactMarkdown + remark-gfm；思维链改用受控显示状态；切换日期清理 savedMsg/followup |

### 工程化加固与格式漂移修复（2026-05-30）

- **工具链**：引入 `ruff`（lint+format）与 `basedpyright`（类型检查）；仓库根 `pyrightconfig.json`（standard 模式、关闭 strict-only 噪音规则）；新增项目级 `CLAUDE.md` 固化命令与工作流。
- **后端类型修复**：basedpyright 从 21 错 → **0 错**。`mineru_client._retry` 补 `TypeVar` 泛型返回类型（消除下游 None 误报）；`conversations.py` 字典解包加 None 守卫；`course_info_service.py` 检索结果标注为 `RetrievedChunk`。
- **前端编译修复**：`CourseInfoPage.tsx` 的 `findLastIndex` 实为 ES2023 方法，在 `lib=ES2022` 下编译失败（此前误判通过——根 `tsconfig` 空跑所致）；升级 `tsconfig.app.json` `lib/target` → ES2023。
- **eslint**：`react-hooks` v7 的 `set-state-in-effect` 对标准"挂载加载"模式误报，降级为 warn；shadcn `ui/` 关闭 `react-refresh` 误报；清理 `ReviewPage` 未使用变量。
- **MinerU 格式漂移**（来自 `format_probe_log.jsonl`）：收录 Excel（`.xlsx`）输入与 `hyperlink` 文本段的 `children` 字段；`normalizer` 对 children 做无损兜底提取；同步更新 `在线API输出文件格式（SaaS推断版）.md` §9.7 与架构文档。格式探针复测 **15/15 全部符合**。
- **git 卫生**：运行时日志 `data/format_probe_log.jsonl` 纳入 `.gitignore`（空=正常，有内容=需排查）。
- **修复 bug：模块九 deadline 天数会过期**。`days_left` 原在卡片生成时算好入库，之后 banner / 卡片一直显示陈旧甚至已过期的天数（实测一个已过 6 天的 DL 仍显示「明天」）。改为 `get_card` 读取时按当天从权威 ISO `date` 字段实时重算；新增 5 条回归测试覆盖。

### 测试与验证

```
v1.2.0 新功能测试（test_v120.py）：91/91 全部通过（LLM mock，隔离临时 DB；含 5 条 deadline 重算回归）
后端类型检查（basedpyright，standard 模式）：0 errors
TypeScript 编译检查（tsc -p tsconfig.app.json）：0 错误
前端 ESLint：0 errors（8 warnings）
前端生产构建（npm run build）：✓ 通过
MinerU 格式探针（离线复测）：15/15 全部符合
```

真机端到端验证（Playwright 驱动浏览器 + 真实 API Key，针对真实课程 KB「程序设计基础实训」/ 188 文件）：
- 树形文件视图：多级文件夹折叠 + 文件类型/大小/状态 + Shift 范围多选提示 ✓
- 对话 RAG：embedding → 混合检索 → rerank（带相关度分数）→ LLM 流式 → Markdown 渲染 → 内联引用 + 引用面板 ✓
- 会话 Fork：分叉跳转新会话且保留原对话历史，主线不受影响 ✓
- 模块九课程管家：LLM 结构化抽取卡片（老师 / 考核 / 截止 / 通知）+ deadline banner + 课程问答输入 ✓

> 仍未自动验证：模块七「追问思维链」的流式显示（代码已补全并通过编译，需带思维链的复习会话在浏览器内确认）；MinerU 对新上传文件的真实解析（按需触发）。

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

- `doc/09班李宇2022210347-本地ai知识库需求分析报告V7.md`（现已更名为 `doc/项目当前情况.md`，见文首「文档体系重构」）：完整重写为项目现状交接文档
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
