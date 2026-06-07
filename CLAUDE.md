# Mini-NotebookLM Copilot — 项目开发指南

迷你版 NotebookLM：本地 AI 知识库系统（本科课程设计）。当前 v1.5.0（开发中，待用户验收）。

## 技术栈
- **后端**：FastAPI + aiosqlite + Qdrant（本地文件模式，单进程文件锁）+ httpx + openai SDK。包管理 **uv**（不是 pip）；Python ≥ 3.11。
- **前端**：React 19 + Vite 7 + TypeScript（strict）+ Tailwind CSS v4 + shadcn/ui；路由 react-router-dom v7；Markdown 用 react-markdown + remark-gfm。
- **文档解析**：MinerU SaaS API（`/api/v4` 精准解析）。
- **嵌入 / 重排 / VLM**：阿里云百炼 DashScope（text-embedding-v4 / qwen3-rerank / qwen-vl-plus）。
- **QA 问答**：多 Provider 可切换（默认 DashScope qwen-plus，可切 DeepSeek/OpenAI/Moonshot）。

## 目录约定
- `backend/app/` — 后端源码：`api/` `services/` `adapters/` `models/` `validators/` `db/` `prompts/`
- `backend/tools/` — 独立脚本（如 MinerU 格式探针）
- `backend/test_*.py` — 端到端 / 阶段测试（**脚本式，非 pytest**）
- `frontend/src/pages/` — 页面；`frontend/src/components/ui/` — shadcn 组件
- `doc/` — 设计与需求文档（见下文「文档」）
- `data/` — 运行时数据：SQLite、Qdrant、MinerU zip、`format_probe_log.jsonl`

## 命令

### 后端
- 安装依赖：`cd backend && uv sync`
- 运行服务：`cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`

**类型检查（两种方式）**：
- **首选 — LSP 插件**：对文件做任意 LSP 操作（如 `documentSymbol`）即可触发诊断推送，日常开发用这个最快。LSP 基于 `pyrightconfig.json`（仓库根），已关闭 strict-only 噪音规则。
- **权威兜底 — CLI**：从**仓库根**运行 `uv run --project backend basedpyright`。当 LSP 插件配置热重载有滞后（刚编辑 `pyrightconfig.json` 后诊断未刷新）时，以 CLI 结果为准。

**代码质量**：
- Lint：`cd backend && uv run ruff check .`（自动修：`--fix`）—— 代码质量检查（逻辑问题、未使用变量等）
- 格式化：`cd backend && uv run ruff format .`—— 代码风格自动排版（引号、缩进、换行等，类似 Black）

- 测试（脚本式，**运行前必须停掉 uvicorn** —— Qdrant 单进程文件锁）：
  - `uv run python test_api.py`（API 端到端）
  - `uv run python test_v120.py`（v1.2.0 功能）
  - `uv run python test_stage2.py` / `test_stage3.py` / `test_stage4.py`
- MinerU 格式探针：`uv run python tools/mineru_format_probe.py [--online]`

### 前端（在 `frontend/` 下）
- 安装：`npm install`
- 开发：`npm run dev`

**类型检查（两种方式）**：
- **首选 — LSP 插件**：TypeScript LSP 提供实时诊断，日常开发最快。
- **权威兜底 — CLI**：`npx tsc -p tsconfig.app.json --noEmit`
  - ⚠️ 根 `tsconfig.json` 是 references-only（`files: []`），直接 `tsc --noEmit` 对它是**空跑、不检查源码**。必须指定 `tsconfig.app.json`。

- 构建：`npm run build`
- Lint：`npm run lint`

## 开发工作流（务必遵循）
改完代码 → 先静态分析 → 再测试 / 试运行。

**静态分析优先级**：
1. **LSP 插件（首选，日常用）**：对修改的文件做任意 LSP 操作（如 `documentSymbol`）触发诊断推送。Python（basedpyright）与 TypeScript 均可用。
2. **CLI 命令（权威，最终验证用）**：LSP 诊断可能有滞后（如 pyrightconfig.json 热重载未生效），上线前跑一次 CLI 确认零错误：后端 `uv run --project backend basedpyright`（仓库根）、前端 `npx tsc -p tsconfig.app.json --noEmit`。

### LSP 注意事项
- LSP 插件提供符号导航（`goToDefinition` / `findReferences` / `hover` / `documentSymbol` 等）+ 被动诊断推送。**涉及"这个函数在哪定义/谁调用了它/它的签名是什么"这类问题，默认走 LSP，不要默认 grep**。grep 只在 LSP 不可用、或要找非符号的纯文本（注释/字符串/配置值）时才上。
- **Python LSP 插件对 `pyrightconfig.json` 热重载有滞后**：刚编辑文件后推送的诊断可能基于尚未完全加载新配置的快照（会残留已关闭的 strict 规则噪音、或误报 venv 内的包「无法解析」）。**权威 Python 类型检查以 CLI `uv run --project backend basedpyright` 为准**；插件诊断仅供参考，必要时重启 LSP server / Claude Code 让配置完全生效。
- pyright 配置放在**仓库根** `pyrightconfig.json`（不是 `backend/`），因为 LSP 插件以仓库根为工作区根。CLI 也需从仓库根运行才能读到同一份配置。配置已关闭一批 basedpyright strict-only 噪音规则，保留能抓真 bug 的检查（None 访问、属性错误、类型不匹配等）。

## 环境变量
后端通过 `backend/.env` 或 **Windows 用户环境变量** 读取配置。必填：`MINERU_API_KEY`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`（DashScope）。
当前开发机已将这两个 key 配置在 Windows 用户环境变量中，无需 `backend/.env` 也能真机运行。模板见 `backend/.env.example`。
**没有这两个 key，文档解析与问答的真机端到端无法运行**；静态分析、前端构建、以及不依赖真实 API 的逻辑仍可验证。

## MinerU 格式漂移监控
MinerU 更新频繁，官网文档更新滞后且有误。本项目以实际调用 MinerU API 测试结果为准，总结归纳出当前版本的实际输出格式（`doc/在线API输出文件格式（SaaS推断版）.md`）。

**每次上传文档解析时**，`pipeline_service` 步骤 [E+] 都跑 `adapters/format_checker.check_bundle` 对 MinerU 返回结果做**全面校验**（不仅是字段层面的增删，还包括已知字段的值是否与推断文档一致——如 `title_level` 当前版本默认输出 1，若实际输出 2/3 也应告警）。发现任何与推断文档不符的情况时追加到 `data/format_probe_log.jsonl`（**无偏差不写**）。

- **盯住 `data/format_probe_log.jsonl`**：文件增长 = MinerU 输出格式发生变化。按 severity 处理：`error` 必修，`warning` 通常需收录新字段/文件/值变化，`info` 酌情。
- 注意：探针主要覆盖「字段/文件」层面的新增或缺失；已知字段内部结构悄悄改变或语义值变化需加强覆盖。当前 `format_checker.py` 侧重字段存在性检查，语义值校验（如 `title_level` 实际值是否符合预期）待加强。
- 出现新格式时同步更新：`doc/在线API输出文件格式（SaaS推断版）.md`、`doc/MinerU to RAG Pipeline 架构设计与数据流方案.md`，以及 `adapters/normalizer.py` + `adapters/format_checker.py` 的已知字段集合。

## 文档

- **`progress.md`（项目根目录）** — 进行中长任务的**实时状态**（在做什么 / 计划阶段 / 自上版以来改了哪些文件怎么改 / 下一步 / 如何验证）。长任务每完成一小步即更新；接手第一篇读它。详见全局 CLAUDE.md「长任务：维护 progress.md」。
- `doc/项目当前情况.md` — 项目此刻已实现到什么程度，**必须与代码一致**（稳定交接快照，每次发版更新）。
- `doc/文档导览.md` — doc 目录导览。
- `doc/MinerU to RAG Pipeline 架构设计与数据流方案.md` — 当前在用的 MinerU 解析/入库方案。
- `doc/在线API输出文件格式（SaaS推断版）.md` — 当前所基于的 MinerU 输出格式推断。
- `doc/mineru/` — 从 MinerU 官网下载的文档（事实来源，原样保留）。
- 阿里云百炼（DashScope）官方文档**不在本地留存**——用到时用 exa / context7 实时检索（大厂文档更新快、手动维护成本高，原 `doc/阿里云模型/` 已删除）。

> 原「下一步开发目标 / 开发实施手册」两篇规划文档已删除，其角色由 `progress.md` 承担（实时计划 + 进度 + 改动记录）。

**文档维护约定**：
- 进行中长任务 → 随时更新 `progress.md`。
- 每轮开发完成后 → 更新 `doc/项目当前情况.md` + README + RELEASE_NOTES。
- MinerU API 出现未知/错误字段 → 更新《在线API输出文件格式（SaaS推断版）》（+ normalizer/format_checker 已知字段集合）。
- 解析入库工作流变化 → 更新《MinerU to RAG Pipeline 架构设计与数据流方案》。

## 约定
- **回复用户用中文**；代码产物（标识符、注释、commit message、PR 描述）用英文。
- 仅在用户明确要求时才 commit / push。
