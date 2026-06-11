# progress.md — Mini-NotebookLM 开发进度

> v1.8.0 功能优化与 Bug 修复全部交付，测试通过。
> **当前进行中：结题（明天结题）—— 见下方「结题任务」。**

---

## 结题任务（2026-06，进行中）

单人结题。老师要求（`doc/结题PPT/` 内两份文档）：项目总结 PPT（计 10 分）+ 每人 5 分钟汇报
（单人做总体总结可适当延长至 ~8 分钟）+ 效果视频 ≤2 分钟 + 工程文件（删公共库留结构）+ 工程说明。

### Phase 0 — 结题材料（✅ 已交付，在 `doc/结题PPT/`）
- `01_结题PPT详细大纲.md` — 15 主页 + 6 附录页逐页内容 + 给 AI PPT 应用的生成提示
- `02_结题演讲稿.md` — 5 分钟核心稿 + 【可延展】段落（→7~8 分钟）
- `03_效果视频分镜脚本.md` — ≤2 分钟分镜（一个问题串起三套透视）
- `04_工程文件说明.md` — 工具/结构/文件→模块映射/代码量(≈2.47 万行)/运行环境/如何运行/打包删库清单
- `结题PPT.html` — **HTML 成品 deck**（1280×720 逐页，键盘翻页/进度条/打印导出 PDF；暖纸赤陶橙「研读室」风）

关键事实基线（已核对代码）：当前代码=v1.8.0 级（HEAD 提交标 v1.7.0 但含 v1.8.0）；
真实模型 `text-embedding-v4`/`qwen3-rerank`/`qwen-vl-plus`/`qwen-vl-max`/QA `qwen-plus`(多 Provider)；
自研代码后端 60 文件 12745 行 + 测试 8 文件 3199 行 + 前端 45 文件 8740 行 + 11 提示词模板。

### Phase 1 — 代码加分项（✅ 已完成，静态全绿；待真机验收）
统一对话组件「通病」（三模块复用 `ChatThread`/`Composer`，改一处全好）：
1. ✅ 多轮检索动效「命令行」→ 新建共享 `components/AgentTimeline.tsx` 决策时间线（问答 + 课程管家复用）
2. ✅ **深度思考串味**：后端 `conversation_service` 新增结构化 `agent` SSE 通道，RAG agent 决策不再走 `thinking`；前端 `ThinkingPanel` 只渲染模型 reasoning，agent 决策走 `AgentTimeline`
3. ✅ 思维链展开/收起自动滚动 → 新建 `hooks/useStickToBottom.ts`（signature 用内容长度，UI 切换不触发）
4. ✅ 深度思考/知识库检索挤输入框 → `Composer` 改两行布局（输入框整行 + 工具条独立行）
5. ✅ 流式抖动 + 不跟随底部 → 移除 `ChatThread` 消息上的 `layout` 动画 + 仅"在底部时"跟随
6. ✅ 来源无「查看原文/跳解析透视」→ 新建 `components/SourcePreview.tsx`（usePdfPreview），ReviewPage/CourseInfoPage 接 onViewSource/onDissectSource
7. ✅ **Agent 决策时间线**：课程管家卡片生成的内联时间线重构为共享 `AgentTimeline`（结构化 round/step/status/queries/missing_analysis/new_queries）

### Phase 2 — 独立 bug（✅ 已完成）
- ✅ 讲义导出 PDF：`api/review.py::export_notes` 两个 pandoc 命令加 `-f markdown-yaml_metadata_block`（修 YAML alias 崩溃），顺手删未用 `import os`
- ✅ 检索透视「检索历史」→ 由常驻左栏改为头部「历史」按钮 + 下拉收纳（`RetrievalXrayPage.tsx`），并修了该文件一处 `catch(e){}` lint error

**改动文件**：后端 `services/conversation_service.py`、`api/review.py`；前端新建 `components/AgentTimeline.tsx`/`components/SourcePreview.tsx`/`hooks/useStickToBottom.ts`，改 `api/types.ts`/`hooks/useConversation.ts`/`components/ChatThread.tsx`/`pages/ChatPage.tsx`/`pages/ReviewPage.tsx`/`pages/CourseInfoPage.tsx`/`pages/RetrievalXrayPage.tsx`。
**质量基线**：basedpyright 0 err（改动文件）· tsc 0 err · eslint 0 err · `npm run build` ✓。
### 验收反馈 · 第 2 轮修复（✅ 已完成，静态全绿）
1. ✅ **深度思考完全没出来**：真机探针证明 `qwen-plus` 开 thinking 会返回 `reasoning_content`；真凶是 `stream_turn` 里**命中图片→走 qwen-vl 多模态模型（不返回 reasoning）→ 思维链被静默关**。修：用户显式开"深度思考"时强制走文本路（图片以 VLM 描述在原位注入），`use_multimodal = has_image and qa_enable_multimodal and not use_thinking`。
2. ✅ **展示实际检索关键词/语义查询**：`RetrievalResult` 加 `plan` 字段；`_fetch_rag_context` 新增 `queries` 步骤，展示 LLM 规划的关键词 chips + HyDE 语义查询（简略版"检索透视"）。
3. ✅ **只显当前阶段 + 完成后自动收起、可展开**：`AgentTimeline` inline 变体重做为折叠式——流式时只显当前阶段一行，完成后自动收成"N 步决策"按钮，点击像思维链一样展开全程。
4. ✅ **导出 PDF 仍失败（无 xelatex/wkhtmltopdf 引擎）**：改为**客户端打印导出**（`#review-print` 屏外容器 + `@media print` 隔离 + `window.print()`），零安装、中文排版完美、浏览器"另存为 PDF"得文件。
5. ✅ **课程管家生成视角跟随**：page scroller 加 `useStickToBottom(pageScrollRef, progressEvents.length)`。

第 2 轮改动文件：后端 `conversation_service.py`/`retrieval_trace.py`；前端 `components/AgentTimeline.tsx`（重写折叠）、`pages/ReviewPage.tsx`（客户端打印）、`pages/CourseInfoPage.tsx`（视角跟随）、`index.css`（打印样式）。

### 验收反馈 · 第 3 轮（✅ 已完成，静态全绿）
> 注：用户中途换机器，仓库经 git 同步到 `C:\Users\14044\Desktop\PyProject\mini-notebooklm-copilot`（旧机为 `C:\Users\Alan\Desktop\PyProj\...`，已弃用）。提交 `85f2665 v1.7.9` 含 round 1+2 全部改动。

1. ✅ **全面改用 qwen-plus**（实测探针 + 阿里云官方文档双重确认：qwen-plus 现为多模态，且可"边看图边输出思维链"）：
   - `config.py`：`vlm_model` 与 `qa_multimodal_model` 默认 `qwen-vl-plus`/`qwen-vl-max` → **`qwen-plus`**。
   - `qa_service.stream_llm_completion`：多模态分支不再无条件关思考；仅 `qwen-vl` 系列才关（qwen-plus 保留思考）。
   - `conversation_service.stream_turn`：**撤销第 2 轮"开思考就降级文本路"**——qwen-plus 多模态+思考可兼得，`use_multimodal = has_image and qa_enable_multimodal`。
2. ✅ **Provider 切换加分项**：原已实现（设置页可编辑 `QA_MODEL`/`QA_BASE_URL`/`QA_API_KEY` → `.user_config.json` → 重启生效）。本轮在设置页加 **Provider 一键预设**（百炼/DeepSeek V3/DeepSeek R1/GPT-4o/Kimi），点击自动填 base_url+模型。

第 3 轮改动文件：后端 `config.py`/`services/qa_service.py`/`services/conversation_service.py`；前端 `pages/SettingsPage.tsx`（Provider 预设）。
质量：basedpyright 0 / tsc 0 / eslint 0 / build ✓；config 运行时加载确认 vlm=mm=qa=qwen-plus。

### Phase 3 — 定稿（✅ 文档已同步；待用户录视频 + 提交）
- ✅ 代码体检：用户已验收；basedpyright 0 / tsc 0 / eslint 0 / build ✓；回归 `test_v120` 130/130 + `test_v140` 86/86 全过；无回归。
- ✅ 项目文档同步：`README.md`（Provider 表更新到 2026-06 当前型号 + 一键预设说明、qwen-vl→qwen-plus）、`doc/项目当前情况.md`（顶部新增 v1.8.0 结题版快照 + 模型名统一）、`RELEASE_NOTES.md`（新增 v1.8.0 结题版条目）。
- ✅ 结题 PPT 材料回填：`结题PPT.html` / `01_详细大纲` / `04_工程文件说明` 模型名 qwen-vl→qwen-plus + 强化"多 Provider 一键切换"加分项；`02_演讲稿` 新增「多 Provider 一键切换」可延展段落。
- ⏳ 待用户：① 用改进后界面录 ≤2 分钟效果视频（分镜见 `03_效果视频分镜脚本.md`）；② 把 PPT 占位框替换为真实截图；③ 按提交清单打包工程文件（删 .venv/node_modules/data/.env）。

---

## v1.8.0 已完成

### 后端 RAG / Q&A 迭代优化
- **Iterative Retrieval Agent**：重构 `_fetch_rag_context` 为异步生成器，引入 `rag_eval_system.md` LLM 评估和第二轮补充检索，将 Agent 检索规划与完整度评估作为 `thinking` 事件流式返回。
- **课程问答与追问检索开关**：在 `course_info` 聊天 API 中支持 `enable_rag`；在 `review` 追问 API 中支持 `enable_rag` 与 `enable_thinking`。
- **只读讲义 Q&A 激活**：支持在 `conversation_id` 为空时传入 `date` 进行追问，后端自动基于该日期创建新会话、载入磁盘讲义作为上下文进行问答。

### 后端讲义 Pandoc 导出
- **Pandoc PDF/Markdown 编译导出**：实现 `POST /api/review/{kb_id}/export` 接口，支持调用本地 `pandoc` 并使用 `xelatex` (CJK 字体 Microsoft YaHei 支持) / `wkhtmltopdf` 编译并下载 PDF/Markdown。

### 前端问答交互与 Composer 增强
- **Composer 检索开关**：在 `Composer` 中增加 `enableRag` 开关与 `ScanSearch` 图标，并在课程问答和课后追问中绑定。
- **流式生成指示器裁剪**：当 `ragMode` 为 False 时自动裁剪显示步骤，防讲义生成或纯对话时误报 "规划检索中"。
- **查看已存讲义问答激活**：修复只读讲义视图，展示 Q&A composer，首发提问自动初始化会话。
- **移除上课描述**：从 Review 页面生成参数表单中移除“上课描述”，并默认传递空字符串给后端。
- **替换 print 导出**：更换 Review 页导出按钮为 handleExport，流式下载编译生成的正式中英双语讲义 PDF。

### 检索透视定位跳转
- **透视-溯源跳转**：为 DemoStages 演示态 Chunks 卡片与 DevTables 开发态数据行绑定 onClick 事件，支持点击跳转并高亮框选定位至 `/kb/${kbId}/dissect?doc={docId}&child={childChunkId}`。

### 回归与类型安全
- **测试通过**：`test_v120.py` (122/122 PASS) 与 `test_v140.py` (86/86 PASS) 回归全部通过。
- **类型安全**：`basedpyright` 0 错误，前端 `tsc` 0 错误，`npm run build` 构建成功。

## v1.7.0 已完成

### Agent 多轮检索过程流式与可视化
- **SSE 流式接口**：`/generate` API 添加 `stream=true` 选项，输出各阶段 JSON 进度通知，并对原有同步返回做 100% 降级兼容，未影响任何测试用例。
- **Agent 状态上报**：服务层封装 `generate_card_stream` 异步迭代器，细粒度流式上报意图检索、片段合并去重、Agent 完整度评估分析和新一轮规划搜索词等中途状态。
- **决策透视时间线**：前端针对提取过程重构为精美的垂直 Timeline 组件，结合 Framer Motion 呈现渐变、高亮与 Agent 决策思考气泡。
- **路由绝对路径修复**：修复了侧边栏菜单使用相对路由时，在多层级路径下导致参数错误拼接跳转至 404 并回退主菜单的 Bug。

## v1.6.0 已完成

### 前端架构重构
- **导航单列化**：Layout.tsx 合并原主菜单 + KB 二级菜单为一列可收起导航
- **文件管理 Explorer 风格**：表格式布局 + 右键菜单（属性/透视/重命名/复制/移动/解析/索引/删除）+ 属性侧面板（切片统计）+ 双击→解析透视
- **设置页可编辑**：QA 模型/API Key/VLM/多模态开关均可前端直接改，智能掩码保护
- **聊天动效**：四阶段流式进度指示器（旋转光晕动画）

### 切片增强
- **父切片空标题合并**：连续空标题文本累积到下一个父块，防信息丢失
- **代码块 LLM 富化**：功能说明 + 核心代码提取 → 子块检索；原始代码 → QA 上下文
- **公式块 LLM 富化**：自然语言含义解释 → 子块检索；原始 LaTeX → QA 上下文

### MinerU 格式校验升级
- 从字段存在性扩展到 19 项语义值检查（完整清单见推断文档 §10.5）
- 新增 `_version_name` 版本号监控、`_backend` 后端类型检查
- 修正预期值：`list_type`、`table_type`、`title.level` 对齐实测
- 推断文档已更新 §10

### 基础设施
- 公网访问（IPv4+IPv6）、并发 2→8、文件夹绑定对所有 KB 类型开放、上传不自动解析
- 文件 rename/copy/move API、音视频文件过滤

### Bug 修复
- API Key 防掩码覆盖（含 `****` 跳过）
- test_v120.py 修复（multimodal 参数、prompts 计数、音频同步断言）

### 质量基线
- `basedpyright` 0 err · `tsc` 0 err · `build` ✓
- `test_v140` 86/86 · `test_v120` 122/122
- Playwright 0 控制台错误

### 文档
- `项目当前情况.md` / `README.md` / `RELEASE_NOTES.md` / `在线API输出文件格式（SaaS推断版）.md` / `MinerU to RAG Pipeline 架构设计与数据流方案.md` 已全部更新至 v1.6.0

---

## 运行 / 验证

- 后端：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 前端：`cd frontend && npm run dev` → http://localhost:5173/
- 测试（先停 uvicorn）：`uv run python test_v140.py`
- 类型：仓库根 `uv run --project backend basedpyright`；前端 `npx tsc -p tsconfig.app.json --noEmit`

## 注意事项
- git 用户手动管理；测试前停 uvicorn；LSP 首选/CLI 权威兜底
- 回复中文，代码英文；环境变量已配 Windows 用户级
