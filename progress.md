# progress.md — Mini-NotebookLM 开发进度

> v1.6.0 全部交付，待用户验收。

---

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
