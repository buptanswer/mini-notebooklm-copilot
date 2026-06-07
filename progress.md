# progress.md — 当前任务进度（接手必读）

> **这是什么**：本项目长任务的**实时状态文件**。给"完全没有上下文的接手者（人或 AI）"看的——
> 让他不读历史对话也能接着干，并知道**自上一个版本以来改了哪些文件、怎么改的、为什么**。
>
> **接手第一步**：读本文 →（按需）读 `doc/项目当前情况.md`（稳定的已实现快照）→ 继续。
> **每完成一小步或调整计划，立即更新本文。**

---

## 0. v1.5.0 本轮（进行中）—— 解析/检索透视深化 + 实现修正

**触发**：v1.4.0 实机验收反馈。审定计划见 `~/.claude/plans/inherited-forging-prism.md`（已批准）。
**关键实验结论（纠正 v1.4.0 误判）**：MinerU 解析请求**按文件加 `is_ocr=true`** → Office 不再走 office backend，被转成 PDF 并产出 bbox。
实测（docx 15KB）：`vlm+is_ocr`→`_backend=hybrid`/40 bbox/含 origin.pdf；`pipeline+is_ocr`→`pipeline`/40 bbox/含 PDF。
→ **Office 可像 PDF 一样坐标渲染，无需 LibreOffice 自转**。
**决策（用户拍板）**：①自定义索引做真功能（生成/存储/开关/编辑 + 接入检索召回）；②父块粒度文档级可设置+重索引（默认 L1）；
③Office 加 `is_ocr` 重解析取坐标；④先解析透视重构 + 演示打磨，再后端正确性/检索质量。
**索引/QA 语义基准**：图/表索引文本=大模型描述；多模态命中图传原图；纯文本路 图→VLM描述、表→MinerU HTML 替换进父块。

**【v1.5.0 中途澄清 + 用户拍板（2026-06-06，关键修正）】**：
- **image_desc/table_desc extra 索引 → 移除（用户拍板）**。原因：**基础管线已实现**用户真实意图——`enricher` 给图块 `embedding_text=caption+VLM描述`、`pipeline_service` 回写 `blk.text`，故 child_chunker 让**每张图/表各成 1 个独立子块**，retrieval_text=`[图片: VLM描述]`/`[表格: VLM摘要]`（实测 `cc-aadd51c94848 | [图片: 这是一张示意图…]`），且 `text_for_generation` 把图/表描述**inline 在原位**。Phase 3-② 的 `_gen_asset_desc`（把父块全部图描述**连成1条→1向量**）是误解，重复且更差（多图被平均稀释，实测特定单图 query 进不了 top20）。→ 删前端 KIND_META/AUTO_KINDS 的这两类 + 后端 `_gen_asset_desc`/`_doc_paths`/相关分支 + 对应测试；ParentView 改为明示「图/表描述已在常规子块/资产中自动索引」。**保留 summary/hypo_question/custom**（真正新增召回角度）。
- **QA 上下文 → 位置 interleave 完全版（用户拍板）**：纯文本路 表 `[表格:caption]`→注入 MinerU HTML（在原位）；多模态路当前 `build_multimodal_user_content` 把图**统一追加在全文之后**（非位置），要改成**按命中父块块序把原图插到 `[图片:desc]` 的位置**（text→image→text 交错），让模型知道图夹在哪两段文字之间。归 Phase 5。

**阶段进度**：
- [x] Phase 1 演示打磨（纯前端：检索透视演示态 视角跟随/节奏可调/动效升级）✅ 真机验证通过
- [x] Phase 2 解析透视·结构层（Office `is_ocr` 取坐标 / 父块大框可点击 / 主菜单按路由收起）✅ 真机验证通过
- [x] Phase 3 后端数据层 —— ①父块粒度 + heading-less 修复 ✅；②自定义索引真功能 ✅（真机端到端通过）
- [x] Phase 4 解析透视·检视层 —— ①Inspector 父块视图 + 索引管理 UI **✅ 真机验证通过**；①b 移除 image_desc/table_desc 冗余索引 **✅ 真机验证通过**；②父块粒度 UI + 重索引/重解析入口 **✅ 前端接线完成，待真机验证**
- [x] Phase 5 后端正确性 —— ①jieba 中文 BM25 **✅ 真机验证通过（keyword 0→20）**；②QA 上下文位置注入 **✅ 真实数据验证（表→HTML、图→原位/原图 text→image→text）**；③跨页核查 **✅ 实证结论 + 修复跨页幽灵空块（真实数据验证 + 回归测试）**

### Phase 5-① jieba 中文 BM25（已完成，真机 keyword 0→20）
- `uv add jieba`；新 `services/cn_tokenizer.py`（`segment`/`segment_tokens`，jieba `cut_for_search` + 去标点；中英混合通用）。
- `db/database.py`：FTS5 索引列 `embedding_text`→`fts_text`（CREATE + 两触发器同改）；`child_chunks` 加 `fts_text` 列（CREATE TABLE + 懒迁移 ALTER）；新增 `_migrate_fts_jieba(db)`：检测旧 FTS（schema 含 embedding_text）→ 删旧 FTS/触发器→按新 schema 重建→对存量 child_chunks 用 jieba 回填 fts_text→`INSERT ... VALUES('rebuild')` 重建索引。纯本地、不触网。**真机：迁移回填 1147 行**。
- `services/index_service.py` `_write_sqlite`：child_chunks INSERT 加 `fts_text=_cn_segment(embedding_text)`。
- `services/index_builder_service.py` `_materialize`：虚拟子块 INSERT 加 `fts_text=_cn_segment(index_text)`（自定义索引也支持中文关键词召回）。
- `services/retrieval_service.py`：`_build_fts_query` 改用 `segment_tokens`（与索引同分词器），`_FTS_MAX_TOKENS` 10→24。
- `services/retrieval_trace.py`：`_kw_tokens_of`（关键词也 jieba 切子词）对齐高亮，`_kw_token_patterns`/`kw_tokens` 共用 → 检索透视中文命中能点亮。
- **真机验证**：3 个中文 query（纯中文）`/retrieve-trace` 的 `keyword` 召回从 **0 → 20**；单元 `test_cn_tokenizer` 6 条。

### Phase 5-② QA 上下文位置注入（已完成，真实数据验证）
- 新 `services/qa_context.py`：`render_qa_sources(chunks, parent_map, *, multimodal)` 读 enriched IR 投影（按 doc_id 缓存）+ assets 表（asset_id→原图路径），按 `parent.block_ids`(order_in_doc) 还原父块：
  - 纯文本 `text`：图→`[图片: VLM描述]`、表→**MinerU HTML**、其余→块文本，**均在原位**；无 block_ids/IR 时回退父块 `text_full`。
  - 多模态 `segments`：文本累积成 text 段，遇有原图的图/表→收尾文本段+发 image 段 → `text→image→text` 交错（图夹在原位）。`sources_have_images` 判定是否走多模态。
- `services/qa_service.py`：新 `build_multimodal_content_from_sources(intro, sources, question)`（按 segments 把图片 `image_url` 插到原位）；保留旧 `build_multimodal_user_content`（旧 /chat 直答端点用）。
- `services/retrieval_service.py` `fetch_parent_chunks`：SELECT 加 `block_ids`（QA 还原父块需要）。
- `services/conversation_service.py`：`_fetch_rag_context` 改用 `render_qa_sources`（返回 (citations, sources, has_image)，sources 带 segments）；`stream_turn` 多模态走 `build_multimodal_content_from_sources(_RAG_INTRO, sources, user_q)`、纯文本走 `_build_rag_content`（现表格已是 HTML）；删除已死的 `_PARENT_CONTEXT_CAP`、`collect_image_paths` 调用。
- **真实数据验证**（03课 PDF pc-d9a6d4346226，27块/12图1表）：纯文本路含 `<table` HTML + `[图片:描述]`；多模态路 segments = `text,image,×13...` 完美交错、13 原图入消息。单元 `test_qa_context_render` 10 条。**注**：旧 `qa_service.stream_answer`(chat.py /chat 直答端点，主聊天 UI 不走) 未改造，仍用简单拼接。
- 基线：`basedpyright` 0；`test_v140.py` **79/79**（+jieba6 +qa_context10，-asset_desc）。

### Phase 5-③ 跨页核查（已完成：实证结论 + 修复跨页幽灵空块）
**用户的问题**：MinerU 自动合并被跨页拆分的块吗？JSON 里看得到吗？我们处理得当吗？
**实证结论（扫了盘上全部已解析文档，34 页设计文档为主样本）**：
1. **MinerU SaaS 的 `content_list_v2.json` 不合并跨页拆分块**，且**没有 `cross_page`/`continued` 之类显式标记**——它严格按页分组。一个跨页编号列表实测为：首页出 `list` 块(项1、2)，次页续接的项3、4变成两个独立 `paragraph` 块（**未并回 list**）。（历史上携带跨页 `lines` 信息的 `middle.json` **不在 SaaS 输出**里，我们只有 content_list_v2 + layout。）
2. **但它在干净的句/项边界断开**：扫 107 个页边界，**0 个**「段落末尾无终止标点 + 次页接段落」的中途断句案例 → 从不把一句话从中间劈开。
3. **我们的 section 切片天然缝合**：父块(Small-to-Big)按 `order_in_doc` 把同 section 跨页块顺序拼接 → LLM 永远看到连续上下文；子块虽按块切窗，但因断点在句界，每个子块仍是完整句 → 检索不受损；逐块 bbox/page 保留 → 溯源高亮正常。**故无需做跨页合并启发式（对 0/107 的问题强行合并反而有误并风险）**。
**但实证中发现一个真 bug（已修）——跨页续表「幽灵空块」**：
- 现象：跨页**表格**在首页给出完整 `html`+表图，次页会再 emit 一个**空 table 块**（`html=""`、`image_source.path="images/"` 只有目录无文件名、caption 空）。
- 危害：这空块经管线→ `retrieval_text="[表格]"` 的**垃圾子块污染检索**（34 页设计文档实测产生 **10 个** `[表格]` 占位子块）+ 一个**指向 images 目录的伪 asset**。
- 修复（双层，源头 + 兜底）：
  - `adapters/normalizer.py`：①`_get_image_source_path` 对「无文件名后缀」的 path（如 `images/`）返回 None（不造伪 asset）；②新 `_is_empty_visual_block`——image/table/equation 且无文本/无 html/无 math/无真实资产 → 在归一化阶段**直接丢弃**（不进 IR/section/chunk/asset）。**关键：不写 `degraded`**（`pipeline_service` 用 `degraded` 非空判 needs_review，写了会让所有含跨页表格的文档被误标）。
  - `chunkers/child_chunker.py`：`_make_atomic_child` 兜底——`retrieval_text` 为纯占位(`[表格]/[图片]/[公式]`)且无真实资产文件 → 不出子块。覆盖「从旧盘上 IR 重切片(reindex)」场景（旧 IR 仍含幽灵块）。
- **真实数据验证**：对 808c0828 跑新 normalizer → 空表块 10→0、伪 asset 0、`degraded` 干净。回归测试 `test_cross_page_empty_block`（7 条）。
- 基线：`basedpyright` 0；`test_v140.py` **86/86**（+跨页7）。

### Phase 6 测试/类型/文档/收尾（已完成）
- **静态检查全过**：`basedpyright` 0/0/0；`test_v140.py` **86/86**；前端 `tsc -p tsconfig.app.json` 0、`eslint`（新增文件 0 error/0 warning，剩 14 个既有 set-state-in-effect warning）、`npm run build` 通过。
- **真机验证（uvicorn :8000 + 前端 :5173 + playwright）**：
  - **Phase 4-② reindex**：34 页设计文档（doc `808c0828`，KB `52842b97`）API reindex → **L1=25 / L2=61 / L3=111 父块**（子块恒 216，子块粒度独立于父块），plvl 持久化、回 L1 复原。
  - **Phase 5c 幽灵块**（同上 reindex 验证 child_chunker 兜底）：reindex 后**垃圾占位子块 10→0**、children 226→216。
  - **GranularityControl UI 全链路**：解析透视头部渲染（粒度下拉 + 应用 + 重新解析）；点「应用」弹两步确认（清自定义索引提示）；UI 触发 reindex → 页面重载（reloadKey 生效）、**0 控制台报错**。
  - `/reparse`、`/reindex` 端点经 OpenAPI 确认已注册；**`/reparse` 未擅自触发**（耗 MinerU/VLM API）。
- **文档沉淀**：`RELEASE_NOTES.md` 加 v1.5.0 完整条目；`README.md` 功能表 +4 行；`doc/项目当前情况.md` 头部/完成状态/质量基线更新；`doc/在线API输出文件格式（SaaS推断版）.md` §9.8 记跨页拆分块行为 + 幽灵块处理；记忆 [[project-current-status]] 更新为 v1.5.0 待验收。
- **progress.md 暂不精简**——按约定待用户验收后再收口。

**v1.5.0 全部交付（Phase 1~6），待用户验收。**

**【接手断点定位（新会话已确认）】**：上一个 AI 在 **Phase 4 起手处**中断。Phase 1/2/3（含 3-①②后端）实体完成且
`basedpyright` 0 / `test_v140.py` 65/65 通过。断点证据：`Inspector.tsx` 已 staged Phase 4 的 import（`ExtraIndex`/
`createDocIndex` 等 14 个）但**全未使用** → tsc 报 14 错；`ParseXrayPage.tsx` 已配线传 `selectedParentId`/
`indexesByParent`/`onSelectParent`/`onRefreshIndexes` 给 `<Inspector>`，但 Inspector 不接这些 prop → 类型错。
即：types.ts/client.ts 的索引 API（`ExtraIndex*` 类型 + `listDocIndexes/createDocIndex/patch/toggle/regenerate/
deleteDocIndex`）与 ParseXrayPage 配线**都已完成**，唯独 **Inspector 的实 UI 没写**。本会话补完 Inspector。

**改动记录（v1.5.0，开工后逐条补）**：

### Phase 1 演示打磨（已完成，真机验证通过）
- `pages/RetrievalXrayPage.tsx`：①节奏可调——新增 `SPEED_MS{slow:3400,normal:2300,fast:1300}` + `speed` state + 工具条"慢/中/快"选择器(Gauge 图标)，自动播放 timeout 改用 `SPEED_MS[speed]`(默认 normal 2300ms，原为固定 1150ms)；②视角自动跟随——每阶段容器挂 `stageRefs`，`revealed` 变化 effect 把当前 StageShell `scrollIntoView({behavior:smooth,block:center})`(仿流式输出视角跟随)；wrap 每个 Stage 加 `scroll-mt-24`。
- `components/xray/shared.tsx` StageShell：①当前阶段站点加呼吸光晕(radial-gradient accent，opacity/scale 循环)；②内容卡进入改 spring(stiffness210/damping24)+scale；③当前卡顶部 accent 流光指示条(width/opacity 循环)。
- `components/xray/DemoStages.tsx`：①StageVector——加 `xray-vglow` 径向渐变光晕、同心圈缓慢旋转(64s/圈)营造纵深、沿连线流动"语义信号"粒子(前6条，x/y transform 安全动画，不碰 SVG r 属性)；②StageRerank——位次变化连线叠加流光(strokeDashoffset 流动虚线)；③StageKeyword——扫描光束改连续扫盘+高亮前沿线。
- **真机验证**：playwright 真实中文 query → scrollTop 随阶段单调推进(s1≈83→s6≈2724，视角跟随确证)；节奏~2.4s/阶段；控制台 0 报错 0 警告；向量阶段截图渲染正常(光晕/旋转圈/连线/分数列)。tsc -p tsconfig.app.json 0 错、eslint 0 error(1 既有 warning 非本次)、build 通过。
- **顺带印证**：`/retrieve-trace` 真机 vector=20/keyword=**0**/fused=15/final=5 —— 中文 BM25 keyword 路确为 0，印证 Phase 5 待修。

### Phase 2 解析透视·结构层（已完成，真机验证通过）
- **Office 取坐标（核心）**：`config.py` 加 `mineru_office_use_ocr: bool=True`；`pipeline_service.py` 加 `_OFFICE_EXTS`/`_is_office_file()`，[A] 步给 Office 文件的 `files[]` 加 `is_ocr=True`(PDF/图片不变)。
  - **原理（实测+官方确认）**：Office 默认走 MinerU `office` backend(无 bbox、不转 PDF)；加 `is_ocr=true` → 强制转 PDF + 版面识别。`is_ocr` 是 **file 级**参数(放 `files[]` 里)，`model_version`/`enable_table` 是顶层；都"仅 pipeline/vlm 有效"。
  - **真机验证**：上传态 docx(选题思路) 经 `/parse` 重解析 → `_backend=hybrid`、产出 `*_origin.pdf`、blocks 有真实 bbox(`[144,102,848,376]`)、`/ir.origin_pdf_path` 非空 → 前端 `canRenderPdf=true`，浏览器里 **canvas 渲染 PDF + bbox 框**(playwright canvasCount=1)。结构与真 PDF 同构，走同一渲染代码。
  - **注**：已索引 Office 要取坐标须"重新解析"，但 `/parse` 拦截 indexed 状态(409) → 需"重置状态再解析"入口，放 Phase 4。
- **父块大框可点击**：`components/dissect/DocCanvas.tsx` 父块框 `div(pointer-events-none)`→可点击 `button`，加 `onSelectSection` prop，点空白区→选父块(块框 z 更高仍优先选块)，hover 透出淡 accent+「父块」标签；`ParseXrayPage.tsx` 传 `onSelectSection={selectSection}`。真机：点父块框右栏切到小节/父块检视。
- **主菜单按路由收起**：`components/Layout.tsx` 用 `useLocation`，`/dissect` 默认收起(`collapsed` 从路由派生 + 仅当前路由有效的手动覆盖 override，无 effect 避免 set-state-in-effect 告警)；KB 二级菜单不动。真机：dissect 页主菜单宽度=68px(收起)。
- **静态检查**：tsc -p tsconfig.app.json 0、eslint 0 error(剩 DocCanvas:59/ParseXrayPage:73 为既有 effect 告警)、控制台 0 报错。

### ⚠️ Phase 2 顺带发现的真 bug（留 Phase 3 修）
- **heading-less 文档 0 父块 0 子块**：无任何标题的文档 → IR 只有 1 个 synthetic 根节点(无子节点、直含正文块)，但 `chunkers/parent_chunker.py` 用 `if section.level==0 and section.synthetic: continue` **无条件跳过 synthetic 根** → 正文不进任何父块 → 0 chunk → 标记 indexed 但**内容完全不可检索**(实测 选题思路.docx parents=0/children=0)。
  - **修法(Phase 3)**：synthetic 根仅当"有子节点(纯容器)"时才跳过；若它是唯一节点/叶子且含正文块，应照常出父块。Phase 3 重写 parent_chunker(加 N 级标题粒度)时一并修 + 重解析验证。
  - 影响面：仅"零标题"文档(短笔记)；带标题的报告/PPT/PDF 不受影响(已验证 03课 PDF 58 父/281 子)。

### Phase 3-① 父块粒度 + heading-less 修复（已完成，单元测试 9/9 通过）
- `config.py`：加 `parent_chunk_heading_level: int = 1`（N 级标题=1 父块，默认 L1，可按文档覆盖）。
- `chunkers/parent_chunker.py`（重写 `build_parent_chunks`，加 `parent_level` 参数）：
  - **粒度算法**：按 `parent_level` 在 section 树切一刀——级别 ≤ N 的 section 各成"组根"，级别 > N 的内容上卷到最近 ≤ N 祖先(`group_root_id`)；每个组根聚合自身+全部后代正文块为 1 父块。
  - **出父块判据改为"组内有无正文块"**（替代旧的 synthetic-root/纯标题容器特判）：组内含 ≥1 个 `role!=auxiliary 且 type!=title` 才出父块。
  - **天然修复 heading-less bug**：有标题文档的 synthetic 根/纯标题章节无正文→跳过；无标题文档的根直含正文→出父块。
- `chunkers/child_chunker.py`：header 前缀 + `ChildChunk.header_path` 字段都改用**块自身的 `blk.header_path`**（父块按粒度聚合变粗后，子块仍保留其所在子标题的上下文，检索更准）。
- `pipeline_service.py`：`build_parent_chunks(..., parent_level=settings.parent_chunk_heading_level)`。
- 测试 `test_v140.py::test_chunker_hierarchy` 改写：L1 粒度=一级标题各 1 父块且聚合子节正文 / L2 粒度=叶子小节各成父块 / 子块保留自身子标题路径 / heading-less 出 1 父块(回归)。`basedpyright` 0。
- **注**：原测试"容器章节不出父块/叶子出父块 len==3"的预期已随新默认(L1 聚合)更新为新断言。
- **集成验证（已通过）**：重启后端(加载新代码)后重解析概要设计 docx → 143 sections(L1=30/L2=46/L3=66) → **25 父块**(L1 聚合生效，旧行为会 100+)/226 子块/origin_pdf=True。父块标题=顶层节(系统概述/总体结构/模块设计/数据库/接口/其他)。
  - **坑**：uvicorn 无 `--reload` 时改了后端代码必须**手动重启**才生效(否则用旧代码，曾误得 20 父块)。
- **待**：per-doc 粒度设置 UI + 重索引入口 → Phase 4。

### Phase 3-② 自定义索引真功能（已完成，真机端到端 + 离线单元 65/65 通过）
**架构定稿：物化虚拟子块**——`parent_extra_indexes` 表是「管理层/source of truth」（定义/开关/可编辑文本/payload）；
enabled 时把 `index_text` **物化**成 `child_chunks` 一行虚拟子块（`index_kind=kind`）+ embed + Qdrant 单点，
复用同一 embedding/FTS/Qdrant/RRF/重排/Small-to-Big 管线参与检索；disabled 时移除该虚拟行。**检索侧零并行管线**，
命中后经 `parent_chunk_id` 天然回父块（Small-to-Big）。检索结果里只剩 enabled 的，**无需过滤逻辑**。

改动文件：
- `db/database.py`：新增 `parent_extra_indexes` 表（index_id/doc_id/parent_chunk_id/section_id/kind/title/index_text/payload/enabled/source/child_chunk_id/qdrant_point_id/时间戳）+ 2 索引；`child_chunks` 加列 `index_kind`（懒迁移，''=常规子块）。
- `models/models_chunk.py`：`ChildChunk` 加 `index_kind: str=""`。
- `services/index_service.py`：`_upsert_qdrant` payload + `_write_sqlite` 写 `index_kind`；`_purge_doc` 加 `DELETE FROM parent_extra_indexes`（重解析时索引随文档重建——父块边界会因粒度变化而变，强行保留映射会错乱）。
- `services/retrieval_service.py`：`RetrievedChunk` 加 `index_kind`；向量路读 payload、关键词路 SELECT `c.index_kind`。
- `services/retrieval_trace.py`：`_hit_brief`/fusion/reranked 带 `index_kind` → 检索透视可标注「命中来自摘要/推测问题索引」。
- `services/index_builder_service.py`（**新**）：5 类索引生成（summary/hypo_question(可预答,默认关)/image_desc/table_desc(复用 enrichment,不额外触网)/custom）+ `_materialize`/`_dematerialize`（虚拟子块↔child_chunks+Qdrant+FTS）+ `generate/set_enabled/update/regenerate/delete/list_doc_indexes`。
- `prompts/index_summary_system.md` + `index_hypo_question_system.md`（**新**）。
- `api/documents.py`：5 个端点（`GET/POST /{kb}/{doc}/indexes`、`PATCH/POST .../{index_id}`(toggle/regenerate)、`DELETE .../{index_id}`），`IndexBuildError`→400。
- 测试 `test_v140.py::test_extra_index_builder`（mock，13 条）：围栏剥离/JSON 解析/资产描述提取/`_row_to_public` 转换。
- **真机端到端验证（临时脚本，已删）**：custom 物化→`vector/hybrid_search` 命中 `index_kind=custom`(hybrid 排第一)→toggle off 虚拟行消失、检索不再命中；summary/hypo_question LLM 生成(6 问)；image_desc 从 VLM 富化提取成功。`basedpyright` 0 错。
- **坑**：①LSP 对新建文件索引滞后（CLI 权威 0 错，插件误报 import unresolved，忽略）；②qdrant local 模式进程退出时 `QdrantClient.__del__` 良性告警（数据已 commit，无害）。
- **待 Phase 4**：前端父块面板接这些 API（生成/开关/编辑/删除可视化）；per-doc 父块粒度 UI + 重解析已索引入口。

### Phase 4-① 解析透视·检视层 —— Inspector 父块视图 + 索引管理 UI（本会话，已写完，待真机验证）
- 先调 `frontend-design` 技能定美学方向（研读室体系内：父块=「标本解剖」；各索引种别=「检索 lens 卡」，启用即 accent 左条+「检索中」徽章=并入混合检索；hypo 默认关+「耗 API」警示）。
- `components/dissect/Inspector.tsx`（重写，补完上一个 AI staged 的 import）：
  - Inspector 由三态→**四态**：`selectedBlock?BlockView : selectedSection?SectionView : selectedParent?ParentView : OverviewView`（block/section 选中时 selectedParentId 也被设但 block/section 优先；只设 parent=点中间父块大框→ParentView）。
  - **新增 `ParentView`（父块视图）**：头部(父块徽章/id/页跨/标题/header_path 面包屑可跳 section + 成员块/子切片/字数三连 Stat) + **`IndexManager`(主角)** + 折叠区(父块全文 / 父块资产 / 成员 MinerU 块 / 常规子切片)。
  - **`IndexManager`**：常规子块行(始终参与不可关) + 4 类 auto 索引(summary/hypo_question/image_desc/table_desc)各为 `IndexCard`(已生成)或 `GenerateRow`(未生成，image/table 无对应块则禁用) + 多条 `custom` `IndexCard` + `AddCustomRow`。顶部「N 路在用」。
  - **`IndexCard`**：`Toggle`(role=switch，启用=物化进检索) + 文本预览(可展开)/编辑(textarea inline) + hypo 显示 Q/A 列表 + 操作(编辑[非hypo]/重生成[非custom，hypo 重生成保持是否预答]/删除[两步确认])；接 `toggle/patch/regenerate/deleteDocIndex`，每次操作后 `onRefreshIndexes()`，per-card busy/err。
  - **`GenerateRow`**：`createDocIndex`(hypo 可勾「附预答」=with_answer)；**`AddCustomRow`**：custom_text 手填。
  - 复用件：`Collapsible`(motion 高度过渡)、`Toggle`、`ActionBtn`、`Stat`、`AssetList`(图片缩略图+「→多模态原图」标注/表/码/式图标)。BlockView/SectionView 的「父切片」卡改为点击 `onSelectParent` 跳父块视图。
  - 仅用设计 token(含新用 `warn`/`success`)；`motion/react` 动效(开关弹簧、折叠高度)；信息密度大→默认折叠、索引区默认展开。
- **静态检查全过**：`tsc -p tsconfig.app.json` 0 错；`eslint Inspector.tsx` 0 problem（ParseXrayPage:78 setState-in-effect 为既有 warning，非本次）；`npm run build` 通过。
- **真机 playwright 验证（全通过，0 控制台报错）**：03课 PDF(b1c79e9e) 文档树点 L1「开发实战:发票提取工具」→SectionView→点「父块视图」卡→ParentView 正常（头部三连 Stat、检索索引面板、父块全文折叠、父块资产13 含图片缩略图+「→多模态原图」+VLM 描述、成员块/子切片）。索引操作：生成 image_desc(无 LLM，12 图描述)→IndexCard、开关 on→「检索中」徽章+「N 路在用」+1、添加自定义索引、生成摘要(LLM 真出一段)、两步确认删除→回到生成行。物化正确(DB: enabled=1 有 child+qdrant_point；disabled 无)，删除幂等(0 孤儿虚拟子块)。
  - **检索接入实证**：`/retrieve-trace` 对匹配 custom 索引文本的 query → 命中 `index_kind=custom`（vector/fusion/reranked 全段带标注，检索透视可标「命中来自自定义索引」）。
  - **顺带发现（报告用户，非本次 bug，归 Phase 5 索引质量）**：`index_builder_service._gen_asset_desc` 把父块内全部图片描述**连成 1 条 index_text → 1 个向量**，多图时该向量被"平均"稀释，特定单图 query 难命中（focused 的 custom 索引则干净命中作对照）。若要 image_desc 真正可召回，应改为**每图 1 条虚拟子块**（架构取舍：N 个 Qdrant 点 vs 1 个；需用户拍板，未擅改）。
- **待**：Phase 4-② 父块粒度 UI + 重索引/重解析入口（**需先补后端**：per-doc 粒度存储 + reindex/reparse 端点，目前 `parent_chunker` 已支持 `parent_level` 参数但 pipeline 只读全局 `settings.parent_chunk_heading_level`，无 per-doc、无重切片端点）。

### Phase 4-② 父块粒度 UI + 重索引/重解析入口（已完成前端接线，待真机验证）
**后端（新增 per-doc 粒度存储 + 不重新解析的重切片端点）：**
- `db/database.py`：`documents` 表加 `parent_heading_level INTEGER DEFAULT 0`（0=全局默认）+ 懒迁移 ALTER。
- `services/reindex_service.py`（**新**）：`rechunk_and_reindex(doc_id, parent_level)`——不触 MinerU，直接读盘上 enriched IR（`DocumentIREnriched.model_validate`），`_reapply_reflow(blocks)`（把 `enrichment.image/table.embedding_text` 回写 `block.text`，与 pipeline 步骤 [E+→L 之间] 同构）→ `build_parent_chunks(..., parent_level=parent_level)` → `build_child_chunks` → `embed_texts` → `index_chunks`（幂等，内部 `_purge_doc` 清旧 chunk/向量/extra_indexes）→ `write_chunks` → 更新 `documents.parent_chunks_path/child_chunks_path/parent_heading_level`。`get_effective_parent_level(doc_id)`：per-doc>0 取之，否则取 `settings.parent_chunk_heading_level`。`ReindexError`。用 `cast("list[IRBlock]", blocks)` 规避 list 不变性。
- `services/pipeline_service.py` 步骤 [L]：`parent_level = await get_effective_parent_level(doc_id)` 后 `build_parent_chunks(..., parent_level=parent_level)`（首次解析也遵守 per-doc 设置）。
- `api/documents.py`：`DocInfo` + `_DOC_SELECT` 加 `parent_heading_level`（COALESCE 0）；`ReindexBody(parent_level)`；`POST /{kb}/{doc}/reindex`（调 `rechunk_and_reindex`，`ReindexError`→400，返回 `{parent_level, parents, children}`）；`POST /{kb}/{doc}/reparse`（重置 status→'uploaded' 后台触发 `run_parse_pipeline`，允许已索引文档重解析取坐标/格式更新）。
**前端：**
- `api/types.ts`：`DocInfo` 加 `parent_heading_level: number`。
- `api/client.ts`：`reindexDocument(kbId, docId, parentLevel)`、`reparseDocument(kbId, docId)`。
- `components/dissect/GranularityControl.tsx`（**新**）：父块粒度 select（一/二/三级标题）+「应用」（二步确认，提示重切片清除自定义索引）+「重新解析」（二步确认，提示耗 MinerU/VLM API）；成功后 `onReindexed()`。
- `pages/ParseXrayPage.tsx`：加 `reloadKey` state（IR/chunks/indexes 三个 effect 都依赖它）+ `selectedDoc` 派生 + 元数据条右侧 `ml-auto` 挂 `<GranularityControl key={docId} currentLevel={selectedDoc?.parent_heading_level ?? 0} onReindexed={()=>setReloadKey(k=>k+1)} />`。
- **静态检查**：前端 `tsc -p tsconfig.app.json` 0 错、`eslint` 我的文件 0 error/0 warning（剩余 14 warning 均为既有 set-state-in-effect）；后端 `basedpyright` 0（上轮已验，本次仅前端接线）。
- **待真机验证**：切粒度→重切片父块数变化 + IR/chunks 重载；重新解析已索引 Office 取坐标。

---

## 1. 上一轮：v1.4.0 —— 技术难点可视化（"唬人"演示版）

**目标**：项目是课程设计，靠 PPT+现场演示答辩。当前前端把解析/检索/切片这些**技术难点全藏起来了**，
演示时老师以为"就调了个 API"。v1.4.0 把真正的难点做成**惊艳、唬人的可视化前端**（在现有"研读室"
设计系统内），同时**修正这些技术的实现偏差**。详细规划见审定计划文件（已批准）。

**纵向切片分阶段**（每阶段端到端可交付）：
- **Phase 1（✅ 完成）：检索透视** —— LLM 生成检索计划(关键词+语义查询) → 关键词+向量双路 → RRF → 重排，
  全链路可视化 + 后端正确性修复（Small-to-Big、多模态问答、图片文本基底）。
- **Phase 2（✅ 完成）：后端数据层** —— LLM 文档树重建、父切片改造、检视接口、小批重解析。
- **Phase 3（✅ 完成，真机验证通过）：前端 MinerU 解析/切片透视**
  （左文档树 + 中版面 bbox 画布 / Office 块流 + 右解析检视 + 可收起侧栏聚焦模式）。
  注：用户机 IDM 曾拦截页面内 PDF（环境问题，用户已在系统托盘 IDM 关掉对 Firefox/Chrome 的下载接管，已解决；详见 §2.6）。
- Phase 4：整合 / 演示模式 / 打磨 / 文档。

**已定决策**：①先做检索透视端到端；②最终问答接入多模态(qwen-vl-max)，命中图片传原图；
③新流水线特性由我挑代表性小批文档重解析验证。

**基线（v1.3.0 + 热修，开工前）**：`test_v120.py` 122/122；`basedpyright` 0 error；前端 tsc/eslint/build 通过。

## 2. Phase 1 任务清单与进度

后端（**全部完成 + 真机验证通过**）：
- [x] `services/query_planner.py` + `prompts/query_plan_system.md`：LLM 生成 {keywords, semantic_query(HyDE陈述句), rewritten}，鲁棒 JSON 解析 + 失败回退朴素分词。**真机验证：source=llm，关键词扩展到位。**
- [x] `services/retrieval_trace.py::run_retrieval_pipeline` + `RetrievalTrace`：规划→双路(向量用semantic_query/关键词用keywords OR)→RRF→重排，全链路 trace。
- [x] 端点 `POST /api/chat/{kb}/retrieve-trace`（chat.py）：纯检索透视，返回 trace + doc 文件名映射。**真机验证：trace 各段齐全，重排能把第12位拉到第1。**
- [x] query_planner 接进 `conversation_service._fetch_rag_context`（真实问答用改进检索）。
- [x] Small-to-Big：`conversation_service` / `qa_service` 上下文改用 parent 全文；`parent_chunks` 加 `text_full` 列(DDL+迁移+写入+回退)。
- [x] 多模态问答：`config` 加 `QA_ENABLE_MULTIMODAL`/`QA_MULTIMODAL_MODEL(qwen-vl-max)`；`child_chunks` 加 `asset_paths`；命中图片传 base64 原图给 vl 模型。**真机验证：vl-max 读图作答"来自图片中的PPT"。**
- [x] 图片文本基底：`normalizer` 弃用 MinerU OCR；`enricher` 提示词改为"描述+转写图中文字"。**真机验证：纯图标得到真实描述、幻灯片图被转写文字。**
- [ ]（待办，提升项）FTS5 中文召回弱（unicode61 对中文不分词），keyword 路主要精确匹配 ASCII；可后续上 jieba 预分词。向量路已兜底中文语义，不阻塞。

前端（**完成 + 真机 playwright 验证通过**）：
- [x] 检索透视界面：演示态脊柱式六阶段动画（查询规划→关键词扫描→语义空间近邻→RRF→重排→终选）+ 开发态密集数据表，由 `/retrieve-trace` 的 trace 驱动。
  - 路由 `/kb/:kbId/xray`（App.tsx），二级侧栏入口「检索透视」(KBLayout.tsx，所有 KB 类型都有)。
  - 类型 `RetrievalTrace*`（types.ts）+ 客户端 `retrieveTrace`（client.ts）。
  - 组件：`pages/RetrievalXrayPage.tsx`（编排 + 播放控制 + 两态切换）、`components/xray/{shared.tsx(组件),helpers.tsx(纯函数),DemoStages.tsx(六阶段),DevTables.tsx(数据表)}`。
  - 样式只用设计 token + motion；向量空间 SVG（半径∝1−相似度，黄金角铺散）、重排交叉连线 SVG（按 child_chunk_id 连接，delta 徽章）。
- [x] **顺带修的后端 bug**：`retrieval_trace` 的 `matched_keywords` 原来用整短语 substring 检查，对 LLM 给的复合关键词（"for 循环"）几乎永不命中 → 关键词高亮形同虚设。改为 **token 粒度命中**（对齐 FTS5 分词）：新增 `matched_tokens`（实际命中 token，前端按词边界高亮，ASCII 用 `\b` 避免 "in" 命中 "printing"）+ 修正 `matched_keywords`（含≥1命中 token 的规划关键词，点亮 chip）。

验证：
- [x] 真机：4 文档新流水线重解析(2 PDF+2 图)；/retrieve-trace 真实 query；多模态 chat 命中图片；`basedpyright` 0 error。
- [x] `test_v140.py` mock 单元回归 **36/36 通过**（含新增 query_planner/trace/多模态助手/Small-to-Big + matched_tokens + 关键词 token 命中回归）。
- [x] 前端 tsc/eslint/build 通过；playwright 真机渲染六阶段 + 开发态 **0 控制台报错、0 横向溢出**。
  - 真机修的两个前端 bug：① 向量脉冲环动画直接动 SVG `r` 属性 → motion 置 undefined 报错，改用 `scale` 变换；② 重排三列 grid 与向量近邻列表 1fr 轨道缺 `min-w-0` → 横向溢出，已补。

## 2.5 Phase 2 任务清单与设计（进行中）

**目标**：补齐 MinerU 解析/切片透视所需的后端数据层 + 修正实现偏差。读懂现有流水线后定下的设计（关键点：MinerU 永远返回 `title_level=1` → `dom_builder` 建出**扁平树**）。

- [x] **A. LLM 文档树重建** `services/doc_tree_service.py`(新) + `prompts/doc_tree_system.md`(新)：
  - `assign_title_levels(blocks) -> blocks`：收集全部 title 块，LLM 推断层级写回 `metadata.title_level`。
  - **输出用「索引回填」`{"items":[{"i":idx,"level":lvl}]}`**（不是定长数组）—— 真机发现 LLM 在 60 个标题上会多/漏几项导致定长数组错位回退；按 `i` 取在范围内的项、缺口用启发式补、覆盖率<0.6 才整体回退，对 LLM 漂移鲁棒。
  - 启发式兜底：数字前缀深度（"1.2.1"→3）/第X章→1/第X节→2/（1）→3；LLM 失败 → 启发式，**绝不阻断解析**。标题数≤1 或 >120 跳过 LLM。
  - 接入：`pipeline_service` 步骤 [G]，`build_dom` **之前** `blocks = await assign_title_levels(blocks)`；`build_dom` 不改。
  - **真机验证（03课 PDF）**：扁平 `{1:60}` → 层级 `{1:14, 2:30, 3:16}`，结构合理（目录→联合主办/…；3、API URL调用流程→准备文件URL/调用API接口/…）。
- [x] **B. 父/子切片改造**（消除"扁平→层级"后退化"纯标题父块"）：
  - `parent_chunker`：非叶容器 section（有 `child_section_ids` 且自身无正文内容块、只有 title）**不出 ParentChunk**；有正文/叶子照常出。
  - `child_chunker`：跳过 `title` 块（标题已在 header_path 前缀里）。
  - parent bbox 并集不进模型，在 /ir 接口按 section 成员块**按页并集**算。**真机：孤儿=0、纯标题 child=0。**
- [x] **C. 检视接口** `api/documents.py` + `services/inspection_service.py`(新，只读)：
  - `GET /{kb}/{doc}/ir`（enriched 兜底 basic → {document, pages(page_size), sections 树, blocks(bbox/type/text/assets/vlm_description/table_html), section_bbox(按页并集)}）、
    `GET /{kb}/{doc}/chunks`（读 jsonl 全字段含 source_block_ids）、`GET /{kb}/{doc}/asset/{asset_id}`（FileResponse，路径限 `DATA_ROOT` 防穿越）。
  - **真机验证（既有 doc）**：/ir enriched=True 61 sections 377 blocks、图片块带 VLM 描述、section_bbox 60；/chunks 60 父 341 子带 source_block_ids；/asset 200 image/jpeg，伪造 id→404。
- [x] **顺带修的 bug**：`index_service.index_chunks` 用新 uuid `INSERT OR REPLACE`，**重解析时旧 uuid 的 chunk/向量不会被覆盖 → 新旧并存重复命中**。加 `_purge_doc(doc_id)`：写入前按 doc_id 清 SQLite(child/parent/assets) + Qdrant 点，重解析幂等。
- [x] **D. 小批重解析 + 验证**：03课 PDF（15 页）真机重解析成功（status→indexed，~2min）。
  - **/ir 层级**：扁平 `{1:60}` → 层级 `{L1:12, L2:32, L3:16}`（真机流水线产出层级树）。
  - **/chunks 无重复**：58 父 / 281 子（不是 60+58=118 → purge 生效，旧 chunk/向量已清）。
  - **/retrieve-trace 正常**：vec=20 kw=20 final=5；深层 header_path 带层级。
- [x] 测试：`test_v140.py` **49/49**（doc_tree 启发式/LLM mock(items)/部分覆盖兜底；层级树→无退化父块/无孤儿/标题不单列）；`basedpyright` 0 error。临时验证脚本用后已删。

**Phase 2 完成。** 由本阶段 /ir /chunks /asset 三个接口驱动 Phase 3。

## 2.6 Phase 3 任务清单与设计（✅ 完成，真机验证通过）

**目标**：把 MinerU 解析 → 结构感知 → LLM 文档树重建 → 坐标锚定 → 父子结构感知切片 → 图片 VLM
多模态适配，这条隐藏流水线揭开成「解析透视」可视化（研读室体系内）。路由 `/kb/:kbId/dissect`，
二级侧栏入口「解析透视」(FileScan 图标，所有 KB 类型；KBLayout.tsx)。三区布局：
左=文档树 outline / 中=版面 bbox 画布(PDF) 或块流(Office) / 右=解析检视。

- [x] **类型 + 客户端**（types.ts / client.ts）：`IRResponse/IRBlock/IRSection/IRPage/IRDocumentMeta/
  SectionBboxEntry`、`ChunksResponse/ParentChunkRow/ChildChunkRow`；`getDocumentIR / getDocumentChunks /
  getAssetUrl`。
- [x] **组件**（`components/dissect/`）：
  - `helpers.ts`（纯）：块类型图例 `TYPE_META`（title/paragraph/list/table/image/code/equation +
    page_header/page_footer/page_number 灰调，X光层位配色，固定 hex 作用在白底 PDF 上）、`normBox`(0~1000→%)、
    `hasGeometry`、`buildSectionTree`(根=无父/父不存在，按 child_section_ids 展开，环/脏数据兜底平铺)、
    `buildMaps`(blockById/sectionById/parentById、blockId→父切片/命中子切片、parentId→子切片、按页/按节块表)。
  - `badges.tsx`（仅组件）：`BlockTypeBadge / TypeDot / LevelTag / MetaPill`。
  - `DocTree.tsx`：交互式 outline（L 徽章、块数、折叠、selected/active 两级高亮，深度缩进）。
  - `DocCanvas.tsx`：react-pdf 渲染 + 每块 bbox 框（类型层位色，selected/hover/同节弱高亮分级）+
    父块并集虚线大框（selected 节突出）+ 翻页 + 图层开关（块框/父块/类型色）。`onRenderSuccess` 后才叠框。
  - `BlockStream.tsx`：Office/无坐标文档降级——按 order_in_doc 铺块卡（类型色左条、图片缩略图 + VLM 描述）。
  - `Inspector.tsx`：三态——①未选→文档总览 + 隐藏流水线竖向叙事（4 步带真实计数）+ 类型图例；
    ②选中 section→成员块类型分布/父切片/子切片/逐块；③选中 block→类型/坐标/原文（图片→/asset 原图 +
    我们的 VLM 描述 + MinerU caption；表格→table_html）+ 所属父切片 + 命中它的子切片。交叉跳转。
- [x] **页面**（`pages/ParseXrayPage.tsx`）：文档选择（仅 indexed/needs_review 且非 txt/md）、加载 /ir+/chunks
  (chunks 缺失不阻断，带请求序号防竞态)、`buildMaps`/`buildSectionTree`/`canRenderPdf` useMemo、
  选块/选节联动（选块跳到块所在页、选节跳到 page_span[0]）、元数据条。route(App.tsx)+nav(KBLayout.tsx)。
- [x] **静态检查**：`tsc -p tsconfig.app.json` 0 错、`eslint` 0 错（修了 BlockStream 渲染期变量重赋值的
  React Compiler 报错，改用「与前一元素比较」）、`build` 通过。
- [x] **真机验证（03课 PDF b1c79e9e，全部通过）**：
  - 文档树 LLM 层级正确（L1/L2/L3）+ 点节点联动高亮；元数据条 377块/61节/58父/281子/78图/VLM富化。
  - 解析检视 section/block 详情、父子切片映射全对；**父切片正文里能看到图片被我们 VLM 描述原位替换**
    （`[图片: 这是一张示意图…]`）——多模态适配难点的直接可视化。
  - **中间栏 PDF 页 + bbox 彩框已验证渲染**：版面块按类型层位色精确框出（title 红陶/image 青/paragraph 蓝/
    页眉脚灰，坐标与 /ir 完全吻合），点框选中块（2.5px 描边高亮）→ 联动右栏 block 详情（类型/坐标/原文）。
  - 收起左右侧栏 → PDF 自适应放大到 900px（演示聚焦模式）。
  - **验证手法**：用户机 IDM 拦截 PDF（见下），故用 Playwright `page.route` 让 Playwright 进程自身取 PDF 再以
    `octet-stream` 回灌（绕开浏览器侧 IDM 钩子，pdf.js 按字节嗅探照常解析），确证前端代码正确。
- [x] **用户机环境问题（已解决，非代码问题）**：用户机的 **IDM (Internet Download Manager)** 是**系统托盘程序**，
  对 Firefox/Chrome 都开了"下载接管"（**程序层接管 + 浏览器扩展两者都装**）。接管是 IDM 程序在监控这两个浏览器的
  下载、不依赖扩展，故按 `application/pdf` 捕获 → 把 react-pdf 的 origin-pdf 请求劫持成下载（弹窗）→ 浏览器侧 fetch
  被中断成 204 → 页面内 PDF 渲染失败；**连无扩展的 Playwright 全新 Firefox 也被钩，正是因为接管在 IDM 程序层而非扩展层**
  （早前误记为"非浏览器扩展/纯系统级"，实为"程序层 + 扩展层都有，程序层接管浏览器进程"）。`curl` 不被钩故直连 200/206。
  **解决（用户已做）**：系统托盘 IDM 设置里关掉对 Firefox/Chrome 的下载接管 → PDF 正常渲染。老师机一般无 IDM 不受影响；
  同理曾影响 ChatPage 引用 PDF 预览。
- [x] **Office 块流 + 真 Chrome PDF 补验（IDM 关闭后，全通过）**：
  - 真 Chrome（IDM 已关）PDF 渲染：canvas + bbox 彩框正常，**0 控制台报错**（IDM 拦截问题确认仅环境层面）。
  - docx（XXX系统需求分析，40块）→ BlockStream 文本块卡（类型徽章 + header 面包屑），无 canvas。
  - pptx（课程介绍2026版，48块/4图）→ BlockStream + **图片缩略图经 /asset 真机加载 + VLM 描述**。
  - xlsx（需求分析评分表，source_format=unknown，1 表格块）→ BlockStream 1 卡，无崩溃、0 报错（兼容退化文档）。

**顺带修的真 bug（已汇报）**：`pdfjs-dist` 被 `^5.4.296` 升到 **5.7.284**，而 react-pdf@10.4.1 内部用
**5.4.296**，pdf.js worker 与 API 版本不匹配（`new URL("pdfjs-dist/build/pdf.worker.min.mjs")` 解析到顶层
5.7.284 worker，API 是 react-pdf 的 5.4.296）→ 控制台 `API version "5.4.296" does not match Worker
version "5.7.284"`，PDF 不渲染。**这个 bug 连 ChatPage 引用 PDF 预览也会坏（潜伏已久）。** 已 `npm install
pdfjs-dist@5.4.296 --save-exact` 钉死到与 react-pdf 一致，清 `.vite` 缓存重启 dev server，版本错误消失。

**关键事实（实现参考）**：
- `IRBlock`：`metadata.title_level`(可变)、`bbox_norm1000.coords`、`bbox_page.coords`、`type`、`order_in_doc`、`assets[].asset_id/path`、`header_path`、`section_id`。`IRSection`：`level/parent_section_id/child_section_ids/block_ids/header_path/page_span/synthetic`。
- `asset.path` 是**绝对路径**（`images_dir.parent/rel`）；`assets` 表有 (asset_id, doc_id, asset_type, path, mime, block_id)。
- enriched IR 落盘 `rag_output_dir/{doc}/document_ir_enriched.json`（含 `blocks[].enrichment.image.image_vlm_description`）；`documents.ir_enriched_path/ir_path/parent_chunks_path/child_chunks_path` 存其路径。
- `call_llm_json(messages, *, model=None) -> str`；`load_prompt("name")` 读 `prompts/name.md` 原文（无 .format，JSON 花括号安全）；解析剥 ```json 围栏（仿 query_planner `_strip_code_fence`）。
- 子块只经 `parent.block_ids` 被 child_chunker 访问 → 跳过的容器 section 的 title 块天然不会变孤儿 child。

## 2.7 Phase 4 计划与进度（进行中）

**目标**：把两个透视页打通进真实问答（"一个问题揭示整条隐藏链路"）+ 文档沉淀。
**决策**：演示模式用**深链打通**（复用已打磨的 RetrievalXray/ParseXray 页，不重写 ChatPage 内联浮层——风险低、演示稳）。

- [x] **A. 检索透视页深链** `RetrievalXrayPage.tsx`：读 `?q=`（+可选 `?k=`）→ 自动填入并跑透视；用过 `setSearchParams({},{replace})` 清 URL。run 重构为 `runQuery(q,k)`（不依赖 state，深链/按钮共用）。
- [x] **B. 解析透视页深链** `ParseXrayPage.tsx`：首渲把 `?doc/?child/?block` 存进 `deepLinkRef`；docs 加载时优先选 `?doc`；maps 就绪后 `block` 直选 / `child`→首个在 maps 内的 source_block → `selectBlock`，清 URL。仅一次（用过把 child/block 置 null）。
- [x] **C. ChatPage 打通** `ChatPage.tsx` + `ChatThread.tsx`：①顶栏「透视检索」（有用户消息才显示）→ `xray?q=<最后一条用户问题>`；②`ChatThread`/`Citations` 加可选 `onDissectSource`，每条来源加「解析透视」→ `dissect?doc=&child=`。纯 additive，Review/CourseInfo 不传该 prop 不受影响。
- [x] **真机验证（全闭环通过，0 控制台报错）**：
  - 直接深链：`xray?q=…` 自动填入+跑通；`dissect?doc=&child=…` 自动选文档+把 child 解析到 source_block 并高亮（1 框选中）。
  - **完整链路**：对话页提问→出答案+5 来源→点「透视检索」跳检索透视自动跑同一问题→点来源「解析透视」跳解析透视，自动选中答案出处的那个块（标题 p.4 #35）并在 PDF 上高亮。验证用的临时会话已删。
- [x] **D. 文档沉淀**：`RELEASE_NOTES.md` 加完整 v1.4.0 条目（4 阶段 + bug + 验证 + IDM 注意）；
  `doc/项目当前情况.md` 头部/完成状态/质量基线 + 模块三(切片)/四(检索)/五(QA)/六(前端路由) 增量更新；
  `README.md` 功能表加 v1.4.0 四行（检索透视/解析透视/正确性/演示模式）。
  **`progress.md` 暂不精简**——按全局约定，待用户验收 v1.4.0 后再把稳定结论收口、精简本文。
- [x] **E. 收尾**：前端 tsc/eslint/build 全过；`basedpyright` 0 错（Phase 4 纯前端未动后端）；演示模式深链全链路 playwright 真机闭环（0 报错）。

**Phase 4 完成（待用户验收）。** v1.4.0 四阶段全部交付。验收通过后：精简 progress.md + 更新 [[project-current-status]] 记忆。

## 3. 接手必须遵守的架构约定（v1.3.0 立下，勿打破）

- **后端对话**：任何"对话/流式"一律走 `conversation_service.stream_turn(...)`，单一 SSE 词汇
  `conversation / message_start / citations / thinking / delta / message_end / done / error`。
- **文本入库**：文本/讲义 .md 走 `text_index_service`（标题分 Parent+空行分段+句窗滑动）；录音 .txt 永不索引；
  `child_chunker._build_windows` 必须逐句消费+长句硬切（有 `_test_chunk_windows` 回归）。
- **外部网络调用**：MinerU/DashScope 包 `services/http_retry.retry_async`；解析受 `_PARSE_SEMAPHORE`(默认2) 限流。
- **前端对话**：复用 `useConversation`+`<ChatThread>`+`<Composer>`，流式只用 `client.ts` 的 `runSSE`；
  样式只用设计 token 工具类 + `Modal`/`Btn`/`Field`；三主题靠 `<html data-theme>`（浅/暗/sepia）。

## 4. 如何运行 / 验证

- 后端：`cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`
- 前端：`cd frontend && npm run dev` → http://localhost:5173/
- 后端测试（**先停 uvicorn**，Qdrant 单进程锁）：`cd backend && uv run python test_v120.py`
- 类型检查：仓库根 `uv run --project backend basedpyright`（权威）；前端 `cd frontend && npx tsc -p tsconfig.app.json --noEmit`
- 真机：playwright-cli；API key 已配在 Windows 用户环境变量，可直接真机测试。

## 5. 注意事项

- **git 由用户手动管理**，AI 不要 commit/push。
- 跑后端脚本测试前必须停掉 uvicorn（Qdrant 单进程文件锁）。
- LSP 插件诊断有滞后，Python 类型以 CLI `basedpyright` 为准；前端 tsc 必须 `-p tsconfig.app.json`。
- 顺手修发现的其它 bug，最后汇报。

## 6. 改动记录（自 v1.3.0 热修以来）

### Phase 1 后端（已完成，详见 §2；真机验证通过）
- `services/query_planner.py`(新) + `prompts/query_plan_system.md`(新)：LLM 检索规划。
- `services/retrieval_trace.py`(新)：`run_retrieval_pipeline` 全链路 + `RetrievalTrace`。
- `api/chat.py`：新增 `POST /{kb}/retrieve-trace` + `_docs_meta`。
- `services/retrieval_service.py`：`keyword_search` 加 `match_mode="or"`、`_build_fts_query` OR 模式、`RetrievedChunk.asset_paths`、`fetch_parent_chunks` 取 `text_full`。
- `db/database.py`：`parent_chunks.text_full` / `child_chunks.asset_paths` DDL + 懒迁移。
- `services/index_service.py`：写入 `text_full` + `asset_paths`（`_build_asset_paths_map`）。
- `services/conversation_service.py` + `qa_service.py`：接 query_planner、Small-to-Big（parent 全文）、多模态问答（命中图片传 base64）。
- `config.py`：`qa_enable_multimodal` / `qa_multimodal_model(qwen-vl-max)` / `qa_multimodal_max_images`。
- `adapters/normalizer.py`：图片 else 分支弃用 MinerU OCR，文本基底=caption（VLM 描述由 enricher 叠加）。
- `enrichers/enricher.py`：图片描述提示词改为「描述 + 转写图中文字」。

### Phase 1 前端（本轮新增，playwright 验证通过）
- `api/types.ts`：新增 `QueryPlan / XrayHit(含 matched_keywords+matched_tokens) / XrayFusionRow / XrayRerankRow / RetrievalTrace / DocMeta / RetrievalTraceResponse`。
- `api/client.ts`：新增 `retrieveTrace(kbId, query, topK)`。
- `App.tsx`：`kb/:kbId` 下加 `xray` 路由。
- `components/KBLayout.tsx`：二级侧栏加「检索透视」(ScanSearch 图标，所有 KB 类型)。
- `pages/RetrievalXrayPage.tsx`(新)：页面编排 —— 查询条 + top-K + 演示/开发两态切换 + 播放/暂停/步进/重播；空态四步预览；加载/错误/空结果态。
- `components/xray/shared.tsx`(新)：纯**组件**（ChunkTypeBadge/ScoreBar/KeywordChip/StageShell/CountBadge）。
- `components/xray/helpers.tsx`(新)：纯**函数**（docName/crumb/fmtScore/isImageType/highlightKeywords，按词边界高亮）。**注意**：组件与函数分文件是为过 eslint `react-refresh/only-export-components`。
- `components/xray/DemoStages.tsx`(新)：六个动画阶段；向量空间 SVG、重排交叉连线 SVG。
- `components/xray/DevTables.tsx`(新)：五张密集数据表。

### Phase 3 前端（本轮新增，部分真机验证；PDF bbox 待 IDM 关闭收尾）
- `api/types.ts`：新增 `IRBlock(Type)/IRSection/IRPage/IRDocumentMeta/SectionBboxEntry/IRResponse` +
  `ParentChunkRow/ChildChunkRow/ChunksResponse`。
- `api/client.ts`：新增 `getDocumentIR / getDocumentChunks / getAssetUrl`。
- `App.tsx`：`kb/:kbId` 下加 `dissect` 路由；`KBLayout.tsx`：二级侧栏加「解析透视」(FileScan)。
- `pages/ParseXrayPage.tsx`(新)：三区编排页。
- `components/dissect/`(新)：`helpers.ts`(纯) / `badges.tsx` / `DocTree.tsx` / `DocCanvas.tsx` /
  `BlockStream.tsx` / `Inspector.tsx`。
- `frontend/package.json`：`pdfjs-dist` `^5.4.296` → 钉死 `5.4.296`（见下「顺带修的 bug」）。

### 本轮顺带修的 bug（已汇报给用户）
- **前端** `pdfjs-dist` 版本漂移：`^5.4.296`→实装 5.7.284，与 react-pdf 内部 5.4.296 的 pdf.js
  worker/API 不匹配 → PDF 不渲染（ChatPage 引用预览也受影响）。已钉死 5.4.296。
1. **后端** `retrieval_trace.matched_keywords`：整短语 substring → token 粒度命中（见 §2），新增 `matched_tokens`。配套回归测试 `test_v140.py::test_keyword_token_match`。
2. **前端** 向量脉冲环：动 SVG `r` 属性触发 motion `Expected length undefined` 报错 → 改 `scale` 变换（DemoStages.tsx StageVector）。
3. **前端** 横向溢出：重排三列 grid + 向量近邻列表 1fr 轨道缺 `min-w-0`（CSS grid min-width:auto）→ 补 `min-w-0`。

### 测试/检查基线（本轮结束）
- `test_v140.py` **36/36**；`basedpyright` 0 error；前端 `tsc -p tsconfig.app.json` / `eslint` / `build` 全过；playwright 六阶段 + 开发态 0 报错 0 溢出。
