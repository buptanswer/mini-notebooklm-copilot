# MinerU 在线 API 输出文件格式（SaaS / `vlm` 请求，实测推断版）

## 1. 文档目的

本文档用于说明 MinerU 官网在线 API 在 `model_version=vlm` 下的实际输出文件格式，并将其整理为一份可复用的通用二次开发参考。

本文档的职责是：

- 说明 SaaS 压缩包内实际会返回哪些文件
- 说明这些文件各自的结构、字段、命名规则和稳定性
- 给出面向通用二次开发的解析建议
- 为后续不同方向的工程方案提供统一事实基础

本文档不负责展开某一个具体应用场景的完整工程设计，例如：

- RAG 切片与索引
- 知识库 IR 设计
- 检索召回链路

这些内容放在单独的方案文档中处理。

### 1.1 文档分工

项目内两份核心文档的职责边界如下：

- [在线API输出文件格式（SaaS推断版）.md](.\在线API输出文件格式（SaaS推断版）.md)
  - 负责说明 MinerU SaaS 输出格式本身
  - 负责说明字段语义、文件命名规则、坐标体系、兼容关系
  - 负责提供通用二次开发建议，适用于 RAG 之外的其他场景
- [MinerU to RAG Pipeline 架构设计与数据流方案.md](.\MinerU to RAG Pipeline 架构设计与数据流方案.md)
  - 负责说明如何把 MinerU SaaS 输出接入多模态 RAG
  - 负责定义 IR、DOM 重建、Parent/Child Chunking、多模态富化等工程方案

建议使用方式：

1. 先阅读本文，确认 SaaS 原始输出格式与稳定字段
2. 再阅读 RAG 架构文档，将这些原始输出映射到具体知识库流程

本文不是开源版旧文档的复述，而是基于以下信息综合整理：

- MinerU 官网下载文档 [输出文件格式（新的）.md](.\mineru\输出文件格式（新的）.md)（官网声称的输出格式，更新滞后、有误，仅供参考）
- MinerU 官网下载文档 [MinerU API 文档（新的）.md](.\mineru\MinerU API 文档（新的）.md)（官网新版 API 文档）
- 你与 MinerU 技术人员的沟通记录
- 2026-03-12 使用 [mineru_vlm_upload.py](.\mineru_vlm_upload.py) 对样本文件的实测结果

## 2. 实测范围

本次实测分两轮：

第一轮代表性采样：

- Word: `test_inputs/sample.docx`
- PPT: `test_inputs/sample.pptx`
- 图片: `test_inputs/sampleJPG/sample-0.jpg`
- PDF: `test_inputs/sample.pdf` 的 `1-5` 页

第二轮扩大覆盖：

- 完整 PDF: `test_inputs/sample.pdf` 全文
- 全部图片: `test_inputs/sampleJPG/*.jpg` 共 13 张

解压后的实测样本目录：

- `test_outputs/extracted/docx`
- `test_outputs/extracted/pptx`
- `test_outputs/extracted/jpg`
- `test_outputs/extracted/pdf`
- `test_outputs/extracted_full/pdf`
- `test_outputs/extracted_full/jpg_all`

重要结论：

- 请求参数虽然是 `model_version=vlm`，但 `layout.json` 顶层元数据中的 `_backend` 实测为 `hybrid`
- SaaS 返回的文件命名规则与开源版旧文档不同
- SaaS 的核心结构化输出并不是旧文档里的 `middle.json`，而是 `layout.json`
- SaaS 比旧文档多出 `content_list_v2.json`、`full.md`、`*_origin.pdf`
- 在扩大覆盖后，完整 PDF 与全部 13 张图片都没有出现新的根目录文件类型，说明核心文件集合相对稳定

## 3. 结果压缩包的实际目录结构

四类样本实测都出现了同一套核心结构：

```text
<zip-root>/
  <uuid>_model.json
  <uuid>_content_list.json
  <uuid>_origin.pdf
  content_list_v2.json
  layout.json
  full.md
  images/
    *.jpg
```

示例：

```text
757d9516-335b-41d5-8474-962ee3cfef85_model.json
757d9516-335b-41d5-8474-962ee3cfef85_content_list.json
757d9516-335b-41d5-8474-962ee3cfef85_origin.pdf
content_list_v2.json
layout.json
full.md
images/...
```

### 3.1 与旧开源文档的映射关系

| 开源版旧文档 | SaaS 在线 API 实际文件 | 结论 |
| --- | --- | --- |
| `{原文件名}_model.json` | `{uuid}_model.json` | 同类文件，命名规则变了 |
| `{原文件名}_middle.json` | `layout.json` | 语义接近，但结构不再等价 |
| `{原文件名}_content_list.json` | `{uuid}_content_list.json` | 同类文件，命名规则变了 |
| `{原文件名}_layout.pdf` | 无 | 本次四类样本均未返回 |
| 无 | `content_list_v2.json` | SaaS 新增，推荐优先消费 |
| 无 | `full.md` | SaaS 新增，Markdown 主结果 |
| 无 | `{uuid}_origin.pdf` | SaaS 新增，标准化后的原始 PDF |
| 无 | `images/*.jpg` | SaaS 新增，供图片/表格/公式引用 |

### 3.2 来自技术人员回复、但本次未实测的部分

根据你提供的沟通记录：

- `layout.json` 对应“中间处理结果”
- `*_model.json` 对应“模型推理结果”
- `*_content_list.json` 对应“内容列表”
- `full.md` 为 Markdown 解析结果
- HTML 文件会有 `main.html`

其中 `main.html` 本次未实测，因为本地调用脚本显式禁止 HTML 输入。

## 4. 命名规则与稳定性判断

### 4.1 命名规则

SaaS 的 zip 包内部并不使用原始文件名作为前缀，而是使用一个任务级 UUID：

- `4899af05-81cb-451b-ac06-964b9367e038_model.json`
- `4899af05-81cb-451b-ac06-964b9367e038_content_list.json`
- `4899af05-81cb-451b-ac06-964b9367e038_origin.pdf`

因此解析程序不能依赖“原文件名 + 固定后缀”。

推荐做法：

1. 先枚举 zip 根目录
2. 按后缀匹配文件角色，而不是按完整文件名匹配
3. 允许 UUID 前缀变化

### 4.2 稳定项

当前可视为较稳定：

- `layout.json`
- `content_list_v2.json`
- `full.md`
- 根目录存在 1 个 `*_model.json`
- 根目录存在 1 个 `*_content_list.json`
- 根目录存在 1 个 `*_origin.pdf`
- `images/` 目录中的相对资源路径

### 4.2.1 面向代码实现的兼容建议

由于 SaaS 输出存在版本波动，后续代码实现不应直接把原始 JSON 当成完全静态协议。

建议实现策略：

- 对 MinerU 原始输出建立显式 Schema 模型
- 原始模型应能够捕获未知字段
- 对已知字段做基础类型校验
- 对缺失的非关键字段允许兼容降级
- 对未知字段至少产生 warning，并保留原始字段内容

如果使用 Python，建议：

- 原始输出层使用 `Pydantic` 宽松建模

原因：

- MinerU 可能增加新字段
- 少数字段在不同版本间可能出现可选性变化
- 如果原始层过严，解析器会因为小改动频繁失效

但要强调：

- “兼容”不等于“静默忽略”
- 任何未知字段都不应被悄悄吞掉
- 最低要求是：记录 warning、保留原始字段、可供后续排查
- 更严格的实现可以提供 strict mode，在发现未知字段时直接失败

但要注意：

- 这只适用于“原始输入层”
- 一旦进入你自己的标准化中间格式，就应该切换为严格模型

### 4.3 不建议硬编码的项

- UUID 前缀本身
- `_version_name`，实测出现 `2.7.5` 和 `2.7.6`
- `_ocr_enable` / `_vlm_ocr_enable`，其值更像服务端执行路径信息，不一定等于你的请求参数回显
- `model.json` 中某些类型是否带 `poly`
- `model.json` 的 `content` 是否一定有值
- 原始 JSON 中未来可能新增的字段集合

## 5. 各文件的实际格式

## 5.1 `*_model.json`

### 5.1.1 推荐定位

低层原始检测结果，适合：

- 调试
- 排障
- 做最底层回溯

不适合直接作为主消费格式。

### 5.1.2 顶层结构

实测是“按页分组的二维数组”：

```json
[
  [ {page0_block1}, {page0_block2} ],
  [ {page1_block1}, {page1_block2} ]
]
```

### 5.1.3 常见字段

实测字段：

- `type`
- `bbox`
- `angle`
- `content`
- `poly`（可选）

实测结论：

- `bbox` 是相对页面尺寸的归一化坐标，范围约为 `0-1`
- `angle` 通常是 `0`
- `poly` 不是稳定字段，只在部分样本/部分块出现
- `poly` 出现时是绝对页面坐标四边形
- `content` 并不稳定

### 5.1.4 一个非常重要的实测差异

对 `docx` 样本，`model.json` 中大量块满足：

- `content = null`
- 但同时存在 `poly`

例如 `title`、`text`、`list`、`page_number`、`page_footnote` 都大量是这种情况。

对 `pdf/pptx/jpg` 样本，`content` 则大多是有值的。

这意味着：

- `model.json` 不能被当成跨格式稳定文本源
- 对 Office 转 PDF 的输入，`model.json` 更像检测框/推理痕迹

### 5.1.5 实测出现过的 `type`

跨样本汇总观察到：

- `title`
- `text`
- `image`
- `image_caption`
- `table`
- `table_caption`
- `table_footnote`
- `equation`
- `list`
- `code`
- `header`
- `footer`
- `page_number`
- `page_footnote`
- `ref_text`

扩大覆盖后的补充观察：

- 完整 PDF 中 `ref_text` 明显增多
- 图片输入并不只会产出纯 OCR 文本，13 张图片聚合后还出现了 `list`、`equation`、`table`、`page_number`、`header`

建议：

- `model.json` 只作为回退和调试输入
- 不要把它当主标准化来源

## 5.2 `layout.json`

### 5.2.1 推荐定位

这是 SaaS 当前最接近旧 `middle.json` 的文件，但它并不是旧 `middle.json` 的原样重命名。

推荐把它视为：

- 页面级中间结构
- 结构回溯层
- 当 `content_list_v2.json` 信息不够时的补充来源

### 5.2.2 顶层结构

实测顶层字段：

```json
{
  "pdf_info": [...],
  "_backend": "hybrid",
  "_ocr_enable": true,
  "_vlm_ocr_enable": true,
  "_version_name": "2.7.6"
}
```

### 5.2.3 与旧 `middle.json` 的主要差异

旧文档中的 `middle.json` 常见字段：

- `preproc_blocks`
- `layout_bboxes`
- `images`
- `tables`
- `interline_equations`
- `_layout_tree`

早期 SaaS 样本的 `layout.json` 中没有这些字段，页面级主要只保留：

- `para_blocks`
- `discarded_blocks`
- `page_size`
- `page_idx`

> **2026-05-21 更新**：新版 MinerU SaaS 输出的 `layout.json` 页面级额外包含 `preproc_blocks` 字段（所有 PDF 类型均稳定出现），对应旧版 `middle.json` 中的同名字段。该字段含 MinerU 内部预处理结果，二次开发通常无需读取，但需列入已知字段表以免误报格式变更告警。

因此不能再按旧 `middle.json` 的字段树直接写解析器。

### 5.2.4 页面级结构

每页实测结构（2026-05-21 更新）：

```json
{
  "para_blocks": [...],
  "discarded_blocks": [...],
  "page_size": [width, height],
  "page_idx": 0,
  "preproc_blocks": [...]
}
```

坐标特征：

- `layout.json` 的 `bbox` 是绝对页面坐标
- 它与 `page_size` 共用同一坐标系
- 可据此换算成 `0-1000` 归一化坐标

### 5.2.5 `para_blocks` 的块形态

实测可分为两类：

简单块：

- `title`
- `text`
- `interline_equation`

这类块通常直接带：

- `bbox`
- `angle`
- `index`
- `lines`

复合块：

- `image`
- `table`
- `list`
- `code`

这类块通常带：

- `bbox`
- `index`
- `type`
- `blocks`
- `sub_type`（部分类型有）

#### `image`

内部通常含：

- `image_body`
- `image_caption`

`image_body.lines[].spans[]` 中会给出：

- `type: "image"`
- `image_path`

#### `table`

内部通常含：

- `table_caption`
- `table_body`

`table_body.lines[].spans[]` 中实测可见：

- `type: "table"`
- `html`
- `image_path`

#### `list`

内部为 `blocks[]`，每个子块一般是一个列表项；实测可见：

- `sub_type: "text"`

根据旧文档与技术人员回复，可以推断后续也可能出现引用类列表，但本次样本未命中。

#### `code`

实测于 PPT 样本中出现，结构包含：

- `sub_type: "code"`
- `guess_lang`
- 子块 `code_body`

### 5.2.6 `discarded_blocks`

这是旧文档里“丢弃块”概念在 SaaS 中的延续，实测出现：

- `header`
- `footer`
- `page_number`
- `page_footnote`

建议：

- 标准化时不要直接丢弃
- 至少保留为 `is_auxiliary=true`
- 后续业务是否忽略，放到上层策略处理

## 5.3 `*_content_list.json`

### 5.3.1 推荐定位

这是旧文档里 `content_list.json` 的 SaaS 兼容版。

优点：

- 已经按阅读顺序展开
- 容易直接消费

缺点：

- 标题被折叠成 `type=text + text_level`
- 页眉/页脚仍沿用旧命名
- 结构比 `content_list_v2.json` 更扁平，语义损失更多

### 5.3.2 顶层结构

顶层是一个平铺数组：

```json
[
  {block1},
  {block2}
]
```

### 5.3.3 坐标系统

实测 `bbox` 为 `0-1000` 范围内的归一化坐标：

- `x_norm = x_abs / page_width * 1000`
- `y_norm = y_abs / page_height * 1000`

这点与 `layout.json` 不同。

### 5.3.4 文本相关规则

标题不会单独保留 `type=title`，而是映射为：

- `type: "text"`
- `text_level: 1/2/...`

正文一般表现为：

- `type: "text"`
- `text_level: 0` 或缺省

### 5.3.5 实测字段

按类型归纳，当前样本中实际出现：

`text`

- `type`
- `text`
- `text_level`
- `bbox`
- `page_idx`

`image`

- `type`
- `img_path`
- `image_caption`
- `image_footnote`
- `bbox`
- `page_idx`

`table`

- `type`
- `img_path`
- `table_body`
- `table_caption`
- `table_footnote`
- `bbox`
- `page_idx`

`equation`

- `type`
- `text`
- `text_format`
- `bbox`
- `page_idx`

`list`

- `type`
- `sub_type`
- `list_items`
- `bbox`
- `page_idx`

`code`

- `type`
- `sub_type`
- `code_body`
- `code_caption`
- `guess_lang`
- `bbox`
- `page_idx`

辅助块：

- `header`
- `footer`
- `page_number`
- `page_footnote`

这些类型通常带：

- `type`
- `text`
- `bbox`
- `page_idx`

## 5.4 `content_list_v2.json`

### 5.4.1 结论

这是 SaaS 最值得优先消费的结构化文件。

原因：

- 保留了页面分组
- 保留了 `title` 与 `paragraph` 的区分
- 不同类型的内容被收纳进 `content` 对象，语义更清晰
- 比 `*_content_list.json` 更接近“标准化接口”

### 5.4.2 顶层结构

顶层是按页分组的二维数组：

```json
[
  [ {page0_block1}, {page0_block2} ],
  [ {page1_block1}, {page1_block2} ]
]
```

### 5.4.3 坐标系统

`bbox` 实测同样是 `0-1000` 归一化坐标。

### 5.4.4 实测类型与 `content` 子结构

`title`

```json
{
  "type": "title",
  "bbox": [...],
  "content": {
    "level": 1,
    "title_content": [
      {"type": "text", "content": "..."}
    ]
  }
}
```

`paragraph`

```json
{
  "type": "paragraph",
  "bbox": [...],
  "content": {
    "paragraph_content": [
      {"type": "text", "content": "..."}
    ]
  }
}
```

`image`

```json
{
  "type": "image",
  "bbox": [...],
  "content": {
    "image_source": {"path": "images/...jpg"},
    "image_caption": [...],
    "image_footnote": [...]
  }
}
```

`table`

```json
{
  "type": "table",
  "bbox": [...],
  "content": {
    "html": "<table>...</table>",
    "image_source": {"path": "images/...jpg"},
    "table_caption": [...],
    "table_footnote": [...],
    "table_nest_level": 1,
    "table_type": "simple_table"
  }
}
```

`equation_interline`

```json
{
  "type": "equation_interline",
  "bbox": [...],
  "content": {
    "math_content": "...",
    "math_type": "latex",
    "image_source": {"path": "images/...jpg"}
  }
}
```

`list`

```json
{
  "type": "list",
  "bbox": [...],
  "content": {
    "list_type": "text_list",
    "list_items": [
      {
        "item_type": "text",
        "item_content": [
          {"type": "text", "content": "..."}
        ]
      }
    ]
  }
}
```

`code`

```json
{
  "type": "code",
  "bbox": [...],
  "content": {
    "code_content": [
      {"type": "text", "content": "..."}
    ],
    "code_caption": [],
    "code_language": "python"
  }
}
```

辅助块命名也更统一：

- `page_header`
- `page_footer`
- `page_number`
- `page_footnote`

注意这里与 `*_content_list.json` 的差异：

- `header` -> `page_header`
- `footer` -> `page_footer`
- `text` -> `paragraph`
- `equation` -> `equation_interline`

扩大覆盖后的补充观察：

- 13 张图片聚合后，`content_list_v2.json` 仍保持相同模式，没有出现新的根结构
- 图片输入除了 `title/paragraph/image`，也可能出现 `list`、`equation_interline`、`table`、`page_number`、`page_header`

## 5.5 `full.md`

### 5.5.1 推荐定位

适合作为：

- 人工阅读结果
- LLM 直接读全文的输入
- 与结构化结果做交叉校验

### 5.5.2 实测特征

- 图片通过相对路径引用，例如 `![](images/xxx.jpg)`
- 标题层级已经被转成 Markdown
- 表格、公式等内容已被渲染成可读结果

建议：

- 如果目标是“保真结构化解析”，不要只依赖 `full.md`
- 但它非常适合做文本召回和人工验收

## 5.6 `*_origin.pdf`

### 5.6.1 推荐定位

这是 SaaS 内部统一后的 PDF 版本，建议作为：

- 页面坐标映射基准
- 页面截图/高亮的源文档
- 非 PDF 源文件的统一承载体

### 5.6.2 实测判断

- `docx/pptx/jpg` 输入也都会得到 `*_origin.pdf`
- 说明 SaaS 在输出阶段统一落到了 PDF 页面坐标系
- 对 PDF 输入，`page_ranges` 选择后，返回结果页数与抽取页数一致，因此可推断 `origin.pdf` 很可能对应本次实际参与解析的页集

最后一句是基于本次 `sample.pdf` 只抽取 `1-5` 页得到的结果推断，不是官方明文承诺。

## 5.7 `images/`

这个目录是所有结构化内容的资源仓库，实测用于：

- 图片正文 `image_source.path`
- 表格截图 `image_source.path`
- 行间公式截图 `image_source.path`
- Markdown 内嵌图片

建议：

- 标准化时保留相对路径
- 在上层再拼接成绝对路径或对象存储 URL

## 6. 给 AI 编程助手的标准化建议

## 6.1 解析优先级

建议的优先级：

1. `content_list_v2.json`
2. `*_content_list.json`
3. `layout.json`
4. `*_model.json`
5. `full.md`

含义：

- `content_list_v2.json` 作为主结构化输入
- `*_content_list.json` 作为兼容层
- `layout.json` 用于补结构、补块内细节、补绝对坐标
- `*_model.json` 只做调试或兜底
- `full.md` 用于全文文本、人工校验和 LLM 直接阅读

## 6.2 推荐的标准中间格式

建议统一成下面这种块级中间格式：

```json
{
  "doc_id": "sample",
  "source_format": "pdf|docx|pptx|jpg",
  "origin_pdf": "4899..._origin.pdf",
  "pages": [
    {
      "page_idx": 0,
      "page_size": [595, 841],
      "blocks": [
        {
          "block_id": "p0-b0001",
          "type": "title",
          "role": "main",
          "bbox": [157, 219, 828, 242],
          "bbox_unit": "norm1000",
          "text": "The response of flow duration curves to afforestation",
          "segments": [
            {"type": "text", "content": "The response of flow duration curves to afforestation"}
          ],
          "attrs": {
            "level": 1
          },
          "assets": [],
          "source_trace": {
            "source_file": "content_list_v2.json",
            "source_type": "title"
          }
        }
      ]
    }
  ]
}
```

字段建议：

- `type`: `title|paragraph|list|table|image|equation|code|header|footer|page_number|page_footnote`
- `role`: `main|auxiliary`
- `bbox`: 统一保存为 `0-1000`
- `segments`: 尽量保留细粒度片段
- `attrs`: 保存 `level/list_type/code_language/table_type/math_type` 等
- `assets`: 保存图片、表格截图、公式截图路径
- `source_trace`: 记录来源文件和原始类型，方便排障

## 6.3 类型映射建议

### 从 `content_list_v2.json` 到标准类型

| `content_list_v2.type` | 标准类型 |
| --- | --- |
| `title` | `title` |
| `paragraph` | `paragraph` |
| `list` | `list` |
| `image` | `image` |
| `table` | `table` |
| `equation_interline` | `equation` |
| `code` | `code` |
| `page_header` | `header` |
| `page_footer` | `footer` |
| `page_number` | `page_number` |
| `page_footnote` | `page_footnote` |

### 从 `*_content_list.json` 到标准类型

| `content_list.type` | 标准类型 | 补充规则 |
| --- | --- | --- |
| `text` | `title` 或 `paragraph` | `text_level > 0` 视为 `title`，否则 `paragraph` |
| `list` | `list` | 保留 `sub_type` |
| `image` | `image` | 保留 `img_path`、caption、footnote |
| `table` | `table` | 保留 `table_body`、`img_path` |
| `equation` | `equation` | 保留 `text_format` |
| `code` | `code` | 保留 `guess_lang` |
| `header` | `header` | 标记 `role=auxiliary` |
| `footer` | `footer` | 标记 `role=auxiliary` |
| `page_number` | `page_number` | 标记 `role=auxiliary` |
| `page_footnote` | `page_footnote` | 标记 `role=auxiliary` |

## 6.4 具体字段提取建议

`title`

- 优先取 `content_list_v2.content.title_content`
- 回退到 `*_content_list.json.text`

`paragraph`

- 优先取 `content_list_v2.content.paragraph_content`
- 回退到 `*_content_list.json.text`

`list`

- 优先取 `content_list_v2.content.list_items`
- 回退到 `*_content_list.json.list_items`

`table`

- 优先取 `content_list_v2.content.html`
- 回退到 `*_content_list.json.table_body`
- 图片路径优先取 `content_list_v2.content.image_source.path`

`image`

- 优先取 `content_list_v2.content.image_source.path`
- 标题/脚注优先取 `content_list_v2.content.image_caption` / `image_footnote`

`equation`

- 优先取 `content_list_v2.content.math_content`
- 回退到 `*_content_list.json.text`
- 图片路径取 `image_source.path`

`code`

- 优先取 `content_list_v2.content.code_content`
- 回退到 `*_content_list.json.code_body`
- 语言优先取 `content_list_v2.content.code_language`，回退 `guess_lang`

## 6.5 解析流程建议

建议解析流程：

1. 解压 zip
2. 建立文件角色索引
3. 优先读取 `content_list_v2.json`
4. 同时读取 `layout.json` 获取 `page_size`
5. 统一生成 `norm1000` 坐标
6. 把辅助块标记为 `role=auxiliary`，不要在底层直接丢弃
7. 记录 `source_trace`
8. 用 `full.md` 生成全文文本缓存

## 6.6 不要这样做

- 不要假设文件名前缀等于原文件名
- 不要假设一定存在 `layout.pdf`
- 不要按旧 `middle.json` 的字段树硬解析 `layout.json`
- 不要把 `model.json` 当稳定文本源
- 不要把 `header/footer/page_number/page_footnote` 在底层直接删除
- 不要把 `_version_name` 写死进解析逻辑

## 7. 已验证事实与推断边界

### 7.1 已验证

以下结论已经被本地样本直接验证：

- SaaS zip 内部核心文件结构
- `layout.json` 的顶层字段与页面级字段
- `content_list_v2.json` 的存在与主要类型
- `*_content_list.json` 的扁平结构
- `*_model.json` 的二维数组结构
- `*_origin.pdf` 的稳定存在
- `images/` 的资源路径引用方式
- `model_version=vlm` 但 `_backend=hybrid`
- 完整 `sample.pdf` 全文 13 页与前 5 页样本在文件结构上保持一致
- `sampleJPG` 全部 13 张图片在核心文件集合上保持一致

### 7.2 基于旧文档/官方回复的推断

以下内容有较强依据，但本次样本未完全覆盖：

- HTML 模式下存在 `main.html`
- `list` 仍可能出现 `ref_text` 类子类型
- 后续版本可能继续扩展 `content_list_v2.json` 的块类型

因此标准化程序应当：

- 对未知 `type` 保留透传
- 把原始块完整挂在 `source_trace.raw` 或等价字段下
- 对未知字段或未知块类型至少产生 warning，不能静默忽略

## 8. 结论

如果后续要做一个稳定、可复用的 MinerU SaaS 解析器，建议采用下面这条原则：

- `content_list_v2.json` 作为主输入
- `layout.json` 作为结构补充和绝对坐标来源
- `*_content_list.json` 作为兼容回退层
- `*_model.json` 只作为调试层
- `full.md` 作为全文阅读层

一句话总结：

> MinerU 在线 API 的 SaaS 输出已经不再等同于开源版旧文档；它的真实主结构化接口，实测上应当理解为 `content_list_v2.json + layout.json + origin.pdf` 这一组三件套。

### 8.1 本文档适合回答什么问题

本文档适合回答：

- 压缩包里有哪些文件
- 哪些文件最值得优先解析
- 每个 JSON 的顶层结构和字段长什么样
- 坐标怎么理解
- 哪些字段稳定、哪些字段不要硬编码
- 如果我要做通用二次开发，应该优先消费哪些文件

### 8.2 本文档不展开什么问题

本文档不详细展开：

- 如何为知识库设计 IR
- 如何重建标题树与 `header_path`
- 如何做 Footnote 拼装
- 如何做 Parent/Child 切片
- 如何做图片描述、表格摘要、检索索引

这些内容请配合阅读：

- [MinerU to RAG Pipeline 架构设计与数据流方案.md](.\MinerU to RAG Pipeline 架构设计与数据流方案.md)

### 8.3 两份文档的配合关系

可以把两份文档理解为上下游关系：

- 本文档回答“MinerU 实际给了我什么”
- RAG 架构文档回答“我应该怎样把这些输出组织成知识库可用的数据流”

也就是说：

- 本文档是格式事实层
- RAG 架构文档是应用工程层

在代码实现层面，也可以这样分工：

- 本文档指导”如何稳健读取 MinerU 原始输出”
- RAG 架构文档指导”如何把这些输出约束成严格的 IR 与 Chunk 模型”

---

## 9. 格式变更追踪（2026-05-21 实测新增）

> 本节记录 2026-05-21 对 `test_inputs/` 下全部文件重新实测后发现的 MinerU 新格式特性，
> 以补充原文档编写时（2026-03-12）未覆盖的变化。

### 9.1 文件命名变更（已在 v1.0.0 修复）

| 文件 | 旧命名 | 新命名 |
|------|--------|--------|
| 内容列表 | `content_list_v2.json` | `{uuid}_content_list_v2.json` |
| 原始文件 | `{uuid}_origin.pdf` | `{uuid}_origin.{源文件扩展名}` |

- DOCX 上传后，origin 文件为 `{uuid}_origin.docx`（不再固定为 `.pdf`）
- PPTX 同理，为 `{uuid}_origin.pptx`
- Office 原生解析时，**不产生 origin.pdf**，PDF 预览功能不可用

### 9.2 新增块类型

#### `chart`（图表）

MinerU 对图表类型进行了专门识别，独立于 `image`：

```json
{
  “type”: “chart”,
  “sub_type”: “line”,
  “bbox”: [87, 376, 440, 551],
  “content”: {
    “image_source”: { “path”: “images/xxx.jpg” },
    “content”: “| Col1 | Col2 |\n| --- | --- |\n| 0 | 10 |”,
    “chart_caption”: [{“type”: “text”, “content”: “Fig. 2. ...”}],
    “chart_footnote”: []
  }
}
```

**关键特性**：
- `content.image_source.path`：图表截图路径（用于多模态 QA）
- `content.content`：MinerU 从图表中提取的结构化数据（Markdown 表格格式）
- `content.chart_caption`：图表标题（`RawTextSegment[]`）
- `sub_type`：图表子类型（`line`, `area_stacked`, `bar` 等，顶级字段）

**解析建议**：映射为 `image` 类型处理，同时将 `content.content`（提取数据）纳入 embedding 文本。

#### `index`（目录/TOC）

Office 原生解析新增 `index` 类型，表示文档目录页：

```json
{
  “type”: “index”,
  “content”: {
    “list_type”: “text_list”,
    “list_items”: [
      {
        “item_type”: “text”,
        “ilevel”: 0,
        “prefix”: “-”,
        “item_content”: [{“type”: “text”, “content”: “第1章 引言”}],
        “anchor”: “_Toc130663182”
      }
    ]
  }
}
```

**解析建议**：映射为 `list` 类型处理（目录条目作为列表项）。

### 9.3 新增块字段

#### 顶级块新字段

| 字段 | 出现场景 | 说明 |
|------|----------|------|
| `anchor` | DOCX 标题/段落 | 文档内部锚点（如 `_Toc130663182`），用于 TOC 超链接目标 |
| `sub_type` | `chart` 块 | 图表子类型（`line`, `area_stacked` 等） |

#### `list` 内容新字段

| 字段 | 说明 |
|------|------|
| `content.attribute` | 列表属性：`”unordered”` 或 `”ordered”` |
| `list_items[].ilevel` | 缩进层级（0 = 顶级，1 = 二级，以此类推） |
| `list_items[].prefix` | 项目符号前缀（`”-”`, `”1.”`, `”    -”` 等） |
| `list_items[].anchor` | 条目锚点（TOC 中使用） |

#### `image` 内容新字段

| 字段 | 说明 |
|------|------|
| `content.content` | 新版 MinerU 对图片内容的 VLM OCR 识别结果（字符串），可直接用于 embedding |

#### 文本段（`RawTextSegment`）新字段

| 字段 | 说明 |
|------|------|
| `url` | `type=hyperlink` 时的目标 URL |
| `style` | Office 原生解析时的字体/样式标记（不用于语义嵌入） |

### 9.4 Office 原生解析（DOCX/PPTX）特性

**核心变化**：DOCX/PPTX 文件现在使用 Office 原生解析引擎，而非 PDF 转换再解析。

| 特性 | 原 PDF 解析 | Office 原生解析 |
|------|-------------|-----------------|
| `bbox` 坐标 | 有效的 norm1000 坐标 | **不提供（键不存在）** |
| `origin.pdf` | 存在，可用于 PDF 预览 | **不存在** |
| 文本分段精度 | 基于 PDF 物理布局 | 基于 Word/PPT 文档语义结构 |
| 图表识别 | 一般作为 image 块 | 有 `chart` 专用类型 |
| 目录页 | 作为普通文本段落 | 有 `index` 专用类型 |

**解析建议**：
- 检测 `bbox` 键是否存在（`”bbox” in block`）来区分两种解析模式
- DOCX 所有块的 `bbox` 键均**不存在**（不是 `null`，是键缺失），使用 `[0,0,0,0]` 占位
- 不要对 Office 原生解析文档开启 PDF 预览功能

### 9.5 `layout.json` 新增页面字段

**`preproc_blocks`**（2026-05-21 格式探针实测）：
- 所有 PDF 类型文档的 `layout.json` 页面级对象中稳定出现
- 对应旧版 MinerU `middle.json` 中的同名字段，含内部预处理块结果
- 二次开发通常**无需读取**（`para_blocks` 已是处理后结果）
- 已加入 `format_checker.LAYOUT_PAGE_KNOWN_FIELDS`，探针不会将其报告为格式变更

### 9.6 代码兼容实现要点

```python
# 判断 bbox 是否实际存在（区分 Office 原生 vs PDF 解析）
has_real_bbox = “bbox” in raw_block and raw_block[“bbox”] is not None

# chart 类型处理
if raw_type == “chart”:
    chart_data = content.get(“content”, “”)  # Markdown 表格数据
    img_path = content[“image_source”][“path”]
    caption = flatten_text_segs(content.get(“chart_caption”, []))
    embedding_text = f”{caption}\n{chart_data}”.strip()

# index 类型：同 list 处理
if raw_type == “index”:
    treat_as_list(content)

# list_item 缩进处理
for item in list_items:
    ilevel = item.get(“ilevel”, 0)
    prefix = item.get(“prefix”, “”)
    indent = “  “ * ilevel
    text = f”{indent}{prefix} {item_text}”.strip()
```


### 9.7 格式探针实测新增（2026-05-23）

> 来源：用户上传文件触发的 `data/format_probe_log.jsonl`。下列两条偏差均已收录并消除（探针复测 15/15 全部符合）。

#### Excel（`.xlsx`）输入支持

- MinerU 现支持 Excel 文件解析，结果包 origin 文件为 `{uuid}_origin.xlsx`（实测 `.xlsx`，推测同样支持 `.xls`）。
- 表格内容以 `table` 块呈现。
- 已加入 `format_checker` 的已知 origin 扩展名清单（`.xlsx` / `.xls`），探针不再报「未预期文件」。

#### 文本段 `children` 字段（hyperlink 嵌套子段）

`type=hyperlink` 的 `RawTextSegment` 新增 `children`：超链接显示文本按样式拆分出的嵌套子文本段数组。

```json
{
  "type": "hyperlink",
  "content": "http://www.icourse163.org/course/BUPT-1003561002（2026",
  "url": "http://www.icourse163.org/course/BUPT-1003561002（2026",
  "children": [
    { "type": "text", "content": "http://www.icourse163.org/course/BUPT-1003561002", "style": ["italic"] },
    { "type": "text", "content": "（", "style": ["italic"] }
  ]
}
```

**关键特性**：
- `children[]` 元素本身是 `RawTextSegment`（含 `type`/`content`/`style`），结构可递归。
- 实测 hyperlink 顶层 `content` 已含链接文本，正常情况不依赖 `children` 也不丢信息。
- 更正：`style` 实测为**字符串列表**（如 `["italic"]`），非单一字符串。

**解析处理（已实现）**：
- `normalizer._flatten_text_segments`：某段 `content` 为空但存在 `children` 列表时，递归提取 children 文本作无损兜底。
- `children` 已加入 `normalizer._KNOWN_TEXT_SEGMENT_KEYS` 与 `format_checker.TEXT_SEGMENT_KNOWN_FIELDS`，探针不再报未知字段。

### 9.8 跨页拆分块的行为（2026-06-06 实测）

> 来源：v1.5.0 跨页核查，扫盘上全部已解析文档（主样本：34 页设计 docx）。这是**行为/语义层面**的观察，
> 非新字段——`format_checker` 是字段级校验，抓不到，故记录在此供维护者参考。

**结论：`content_list_v2.json` 严格按页分组、不合并跨页拆分块，也没有 `cross_page`/`continued` 之类显式标记。**
- 一个跨页编号列表实测：首页出 `list` 块（项 1、2），次页续接的项 3、4 变成两个独立 `paragraph` 块（**未并回 list**）。
- 但断点落在**干净的句/项边界**：扫 107 个页边界，0 个「段落末尾无终止标点 + 次页接段落」的中途断句。
- （历史上携带跨页 `lines` 信息的 `middle.json` **不在 SaaS 输出**里，只有 content_list_v2 + layout。）
- 我们的 section 父子切片天然缝合（父块按阅读序拼接同 section 跨页块、子块按句界切窗），**无需做跨页合并**。

**⚠ 跨页表格的「空幽灵块」（已在 normalizer 处理）**：跨页**表格**在首页给出完整 `html`+表图，**次页会再 emit 一个
空 table 块**——`html=""`、`image_source.path="images/"`（只有目录、无文件名）、caption 空。

```json
{ "type": "table", "content": { "html": "", "image_source": { "path": "images/" }, "table_caption": [] }, "bbox": [...] }
```

- 危害（修复前）：经管线变成 `retrieval_text="[表格]"` 的垃圾子块污染检索（34 页文档实测 10 个）+ 一个指向 images 目录的伪 asset。
- 处理（已实现，v1.5.0）：
  - `normalizer._get_image_source_path`：path 无文件名后缀（如 `images/`）→ 返回 None（不造伪 asset）。
  - `normalizer._is_empty_visual_block` + `normalize()` 主循环：image/table/equation 且无文本/无 html/无 math/无真实资产
    → 归一化阶段直接丢弃。**注意：不写 `degraded`**——否则 `pipeline_service` 会因 `degraded` 非空把含跨页表格的文档误标 `needs_review`。

## §10 v1.6.0 格式发现（2026-06-07 实测，Office/is_ocr 模式）

以下发现来自对 docx/pptx 文件（`mineru_office_use_ocr=True`）的真实解析结果。

### §10.1 title.level 在不同源格式下的行为

当前 MinerU 版本（实测 3.1.8–3.2.1）的 `title.level` 行为：

| 源格式 | 解析模式 | title.level | 说明 |
|--------|---------|-------------|------|
| PDF | vlm (默认) | 1 | MinerU 不做层级识别 |
| Office (docx/pptx) | is_ocr=true → hybrid | 2 | MinerU 在 is_ocr 模式下可能检测到部分层级 |

`title.level` 可能范围为 1–3。format_checker 仅对超出此范围的值告警。

### §10.2 新增 list_type 值

实测发现 `content.list_type` 除了已有的 `"ordered"` / `"unordered"` 外，还包括：

| 值 | 出现场景 |
|----|---------|
| `"text_list"` | Office/pptx 中的文本列表（非编号/非项目符号） |
| `"reference_list"` | PDF 中的参考文献列表 |

normalizer 将这些值原样保存到 `IRBlock.metadata.list_type`，不做特殊处理。

### §10.3 新增 table_type 值

实测发现 `content.table_type` 除了已见过的 `"simple"` / `"complex"` / `"normal"` / `""` 外，还包括：

| 值 | 出现场景 |
|----|---------|
| `"simple_table"` | Office/pptx 简单表格 |
| `"complex_table"` | PDF 复杂表格（含合并单元格等） |

normalizer 将这些值原样保存到 `IRBlock.metadata.table_type`。

### §10.4 _backend 后端类型

layout.json 的 `_backend` 字段指示 MinerU 实际使用的解析后端：

| 值 | 含义 |
|----|------|
| `"vlm"` | 纯 VLM 模式 |
| `"hybrid"` | 混合模式（PDF 转图片 + OCR + VLM）—— is_ocr=true 的 Office 文件落在此 |
| `"pipeline"` | 纯 pipeline 模式 |
| `"office"` | Office 原生解析（无 bbox 坐标） |

format_checker 对未知 `_backend` 值告警。

### §10.5 format_checker 当前覆盖的语义检查清单 (v1.6.0)

| 检查项 | 位置 | 预期值 |
|--------|------|--------|
| title.level | content_list_v2 → title.content | 1–3 |
| list.attribute | content_list_v2 → list.content | `"ordered"` / `"unordered"` |
| list.list_type | content_list_v2 → list.content | `"ordered"` / `"unordered"` / `"text_list"` / `"reference_list"` |
| table.table_type | content_list_v2 → table.content | `"simple"` / `"complex"` / `"normal"` / `"simple_table"` / `"complex_table"` / `""` |
| equation.math_type | content_list_v2 → equation.content | `"latex"` / `"mathml"` / `"asciimath"` |
| code.code_language | content_list_v2 → code.content | str 或 null |
| image_source.path | content_list_v2 → image/chart.content | 以 `"images/"` 开头 |
| list_items[].ilevel | content_list_v2 → list.content | ≥ 0 |
| list_items[].prefix | content_list_v2 → list.content | str 或 null |
| TextSegment.url | content → …_content[] | str 或 null |
| TextSegment.style | content → …_content[] | str 或 null |
| TextSegment.children | content → …_content[] | list（递归校验） |
| _version_name | layout.json | 与 `KNOWN_MINERU_VERSION` 比对（当前 "3.2.0"） |
| _backend | layout.json | `"vlm"` / `"hybrid"` / `"pipeline"` / `"office"` |
| _ocr_enable | layout.json | bool 或 null |
| _vlm_ocr_enable | layout.json | bool 或 null |
| 块类型 | content_list_v2 → block.type | 已知白名单 |
| 块字段 | content_list_v2 → block.* | 已知白名单 |
| content 字段 | content_list_v2 → block.content.* | 按类型白名单 |
| ZIP 文件结构 | 解压目录 | 已知文件白名单 |
  - `child_chunker._make_atomic_child`：兜底跳过「纯占位文本(`[表格]`/`[图片]`/`[公式]`) 且无真实资产文件」的原子块（覆盖从旧盘 IR 重切片(reindex)场景）。
