# progress.md — Mini-NotebookLM 开发进度

> v1.8.0 功能优化与 Bug 修复全部交付，测试通过。

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
