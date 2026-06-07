# progress.md — Mini-NotebookLM 开发进度

> **接手者第一步读这个**。v1.6.0 全部交付，待用户验收。

---

## v1.6.0 交付清单

### 导航重构（单列设计）
- `components/Layout.tsx` — 合并原主菜单 + KB 二级菜单为一列；进入 KB 后菜单自动切换为 KB 子导航
- `components/KBLayout.tsx` — 精简为 deadline banner + 内容区（侧栏移走）

### 文件管理重构（Explorer 风格）
- `pages/KBFilesPage.tsx` — 完全重写：表格布局（格式/大小/页数/状态列）、右键菜单、属性侧面板、双击→解析透视
- `api/documents.py` — 新增 `GET /{kb}/{doc}/stats` 统计端点、音视频文件过滤、xlsx 支持
- `api/types.ts` — 新增 `DocStats` 接口
- `api/client.ts` — 新增 `getDocStats` 函数

### 设置页可编辑
- `api/settings.py` — 新增 `GET/POST /api/settings`，配置持久化到 `backend/.user_config.json`
- `config.py` — 启动时加载 user_config 覆盖
- `pages/SettingsPage.tsx` — 重写为可编辑表单（QA模型/API Key/VLM/多模态开关）

### MinerU 格式校验加强
- `adapters/format_checker.py` — 新增 title.level 语义值检查（预期=1，若≠1 告警）

### 课堂录音处理
- `services/folder_sync_service.py` — 跳过音视频文件（.m4a/.mp3/.mp4 等）
- `api/documents.py` — 上传时拒绝音视频文件、xlsx/xls 支持

### 聊天界面动效
- `components/ChatThread.tsx` — 新增 StreamingIndicator：流式生成时展示四阶段进度（规划检索→混合检索→深度思考→撰写回答），带动画旋转光晕

### Bug 修复
- `main.py`：版本号 1.2.0→1.5.0
- `test_v120.py`：mock 签名补 multimodal 参数、prompts 计数 5→9、音频同步测试适配

### 质量基线
- `basedpyright`: 0 errors
- `tsc -p tsconfig.app.json --noEmit`: 0 errors
- `npm run build`: 通过
- `test_v140.py`: 86/86
- `test_v120.py`: 122/122

---

## 运行 / 验证

- 后端：`cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`
- 前端：`cd frontend && npm run dev` → http://localhost:5173/
- 测试：`cd backend && uv run python test_v140.py`（先停 uvicorn）
- 类型：仓库根 `uv run --project backend basedpyright`；前端 `npx tsc -p tsconfig.app.json --noEmit`
- 真机测试：`C:\Users\14044\Desktop\test\程序设计基础实训`

## 注意事项
- git 用户手动管理；测试前停 uvicorn；LSP 首选/CLI 权威兜底
- 回复中文，代码英文；环境变量已配 Windows 用户级
