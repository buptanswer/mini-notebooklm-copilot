# progress.md — 当前任务进度（接手必读）

> **这是什么**：本项目长任务的**实时状态文件**。给"完全没有上下文的接手者（人或 AI）"看的——
> 让他不读历史对话也能接着干，并知道**自上一个版本以来改了哪些文件、怎么改的、为什么**。
>
> **接手第一步**：读本文 →（按需）读 `doc/项目当前情况.md`（稳定的已实现快照）→ 继续。
> **每完成一小步或调整计划，立即更新本文。**

---

## 1. 当前状态：v1.4.0 开发中 —— 技术难点可视化（"唬人"演示版）

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
