# progress.md — 当前任务进度（接手必读）

> **这是什么**：本项目长任务的**实时状态文件**。给"完全没有上下文的接手者（人或 AI）"看的——
> 让他不读历史对话也能接着干，并知道**自上一个版本以来改了哪些文件、怎么改的、为什么**。
>
> **接手第一步**：读本文 →（按需）读 `doc/项目当前情况.md`（稳定的已实现快照）→ 继续。
> **每完成一小步或调整计划，立即更新本文。** 任务验收后把稳定结论沉淀到
> `README` / `RELEASE_NOTES` / `doc/项目当前情况.md`，并精简本文。

---

## 1. 当前状态

**v1.3.0 已通过用户验收并定稿**（用户自行 git 上传）。当前**无进行中的开发任务**——
等待用户给出使用过程中的体验问题清单，据此开 **v1.4.0**。

- v1.3.0 做了什么、改了哪些文件、6 个验收问题如何处置 → 已全部沉淀到
  **`RELEASE_NOTES.md` 的 v1.3.0 段** + **`doc/项目当前情况.md`**（与代码一致的稳定快照）。
- 质量基线（定稿时实测）：后端 `test_v120.py` **105/105**；`basedpyright` standard **0 error**；
  前端 `tsc -p tsconfig.app.json`（项目本地 5.9.3）**0 error**、`eslint` **0 error**（11 warning）、
  `npm run build` 通过；真机 playwright 渲染验证（首页/复习页/三主题，0 控制台报错）。

## 2. 接手 v1.4.0 必须遵守的架构约定（v1.3.0 立下，勿打破）

- **后端对话**：任何"对话/流式"一律走 `conversation_service.stream_turn(...)`，发**单一 SSE 词汇**
  `conversation / message_start{role,message_id,metadata} / citations / thinking / delta / message_end / done / error`。
  端点只负责外层包 `conversation`…`done`。不要再各写一套流式实现。
- **文本入库**：文本/讲义 .md 走 `text_index_service`（标题分 Parent + 空行分段 + 句窗滑动，**非整段**）；
  **录音转写 .txt 永不索引**（`is_indexable_text`）。切片改动务必保证 `child_chunker._build_windows`
  逐句消费、长句硬切——别退回 `while` 重试写法（曾死循环冻结事件循环，见 `_test_chunk_windows` 回归）。
- **外部网络调用**：MinerU / DashScope 等都包 `services/http_retry.retry_async`；解析受
  `pipeline_service._PARSE_SEMAPHORE`（`MAX_CONCURRENT_PARSES`，默认 2）限流，别 N 路齐发。
- **前端对话**：任何对话页复用 `useConversation` + `<ChatThread>` + `<Composer>`；流式只用
  `client.ts` 的单一 `runSSE`。思维链/历史用函数式 state 更新（别整体覆盖 Map）。
- **前端样式**：颜色/字体只用设计 token 工具类（`bg-bg/surface/surface-2`、`text-ink/ink-soft/ink-faint`、
  `border-border`、`bg-accent/accent-soft`、`text-accent/accent-ink`、`font-display/sans/serif`、
  `shadow-card/raised/pop`、`card` 类）；弹窗用 `Modal`，按钮/输入用 `Btn`/`Field`；三主题靠 `<html data-theme>`。

## 3. Roadmap（v1.4.0 起）

- **v1.4.0**：用户使用体验问题清单 —— **待用户逐条给出后再规划实施**。
- **提升项（未实现）**：模块八 AI 考官（Markdown 题库→智能组卷→MinerU 解析答卷+LLM 逐题判分）；
  音视频转写（飞书妙记/通义听悟）；视频关键帧抽取；FTS5 中文分词（jieba）。
- 完整产品需求/愿景：原 `doc/下一步开发目标.md`（已删）全文可从 v1.2.0 git 历史找回。

## 4. 如何运行 / 验证

- 后端：`cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`
- 前端：`cd frontend && npm run dev` → 打开 http://localhost:5173/
- 后端测试（**先停 uvicorn**，Qdrant 单进程锁）：`cd backend && uv run python test_v120.py`
- 类型检查：仓库根 `uv run --project backend basedpyright`（权威）；前端 `cd frontend && npx tsc -p tsconfig.app.json --noEmit`（用项目本地 tsc，别让 `npx` 从仓库根抓到别的版本）
- 真机：playwright-cli（`open/goto/screenshot/console`）

## 5. 注意事项

- **git 由用户手动管理**，AI 不要 commit/push。
- 跑后端脚本测试前必须停掉 uvicorn（Qdrant 单进程文件锁）。
- LSP 插件诊断有滞后，Python 类型以 CLI `basedpyright` 为准。
