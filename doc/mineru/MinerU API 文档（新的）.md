> 本文由 [简悦 SimpRead](http://ksria.com/simpread/) 转码， 原文地址 [mineru.net](https://mineru.net/apiManage/docs)

> MinerU API 开发者文档，提供完整的 PDF 文档解析 API 接口说明、调用示例和集成指南。支持 RESTful API、Python SDK，快速接入高质量文档解析能力。

MinerU 提供两种文档解析 API，满足不同场景需求：

*   🎯 **精准解析 API** — 需申请 Token，支持单文件 / 批量、表格 / 公式 / 多格式输出
*   ⚡ **Agent 轻量解析 API** — 免登录，IP 限频防滥用，专为 AI Agent 工作流设计

[](#模式对比)模式对比
=============

<table node="[object Object]"><thead><tr><th>对比维度</th><th>🎯 精准解析 API</th><th>⚡ Agent 轻量解析 API</th></tr></thead><tbody><tr><td>是否需要 Token</td><td>✅ 需要</td><td>❌ 无需（IP 限频）</td></tr><tr><td>接口地址</td><td><code node="[object Object]">/api/v4/extract/task</code> 或 <code node="[object Object]">/api/v4/file-urls/batch</code></td><td><code node="[object Object]">/api/v1/agent/parse/url</code> 或 <code node="[object Object]">/api/v1/agent/parse/file</code></td></tr><tr><td>模型版本</td><td><code node="[object Object]">pipeline</code>（默认）/ <code node="[object Object]">vlm</code>(推荐) / <code node="[object Object]">MinerU-HTML</code></td><td>固定 pipeline 轻量模型</td></tr><tr><td>文件大小限制</td><td>≤ 200MB</td><td>≤ 10MB</td></tr><tr><td>页数限制</td><td>≤ 200 页</td><td>≤ 20 页</td></tr><tr><td>批量支持</td><td>✅ 支持（≤ 200 个）</td><td>❌ 单文件</td></tr><tr><td>输出格式</td><td>Zip 包，其中包含 Markdown、JSON，且可导出为 docx/html/latex</td><td>仅 Markdown（CDN 链接）</td></tr><tr><td>调用方式</td><td>异步（提交 → 轮询）</td><td>异步（提交 → 轮询）</td></tr></tbody></table>

[](#-精准解析-api)🎯 精准解析 API
=========================

> 需申请 Token，支持 pipeline / vlm / MinerU-HTML 三种模型，单文件和批量均支持。

[](#概述)概述
---------

MinerU 的精准解析 API 专为需要高精度、深层次结构化提取的复杂文档设计。它能够智能识别并处理各类复杂版式、多模态内容（如表格、数学公式、图表、图片、多栏布局等），将文档内容转化为高质量的结构化数据。

**核心特性：**

*   **极致精度**：提供行业领先的解析准确性，尤其擅长处理非标准和复杂文档
*   **深度结构化**：不仅仅是文本提取，更能深度理解文档的版面和语义，输出包含丰富层级关系的结构化数据
*   **多模态支持**：全面支持文本、表格、图片、公式等多种内容类型的精准识别与提取
*   **复杂版式适应**：有效应对扫描件、排版混乱、水印干扰等复杂文档场景

**文件限制：**

<table node="[object Object]"><thead><tr><th>限制项</th><th>限制值</th></tr></thead><tbody><tr><td>文件大小上限</td><td>200 MB</td></tr><tr><td>文件页数上限</td><td>200 页</td></tr><tr><td>支持文件类型</td><td>PDF、图片（png/jpg/jpeg/jp2/webp/gif/bmp）、Doc、Docx、Ppt、PPTx、Xls、Xlsx</td></tr></tbody></table>

[](#1单个文件解析)1. 单个文件解析
---------------------

### [](#创建解析任务)创建解析任务

**接口说明**

适用于通过 API 创建解析任务的场景，用户须先申请 Token。 注意：

*   单个文件大小不能超过 200MB, 文件页数不超出 200 页
*   每个账号每天享有 1000 页最高优先级解析额度，超过 1000 页的部分优先级降低
*   因网络限制，github、aws 等国外 URL 会请求超时
*   该接口不支持文件直接上传
*   header 头中需要包含 Authorization 字段，格式为 Bearer + 空格 + Token

**Python 请求示例（适用于 pdf、doc、ppt、excel、图片文件）：**

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "vlm"
}

res = requests.post(url,headers=header,json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])
```

**Python 请求示例（适用于 html 文件）：**

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "url": "https://****",
    "model_version": "MinerU-HTML"
}

res = requests.post(url,headers=header,json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])
```

**CURL 请求示例（适用于 pdf、doc、ppt、excel、图片文件）：**

```
curl --location --request POST 'https://mineru.net/api/v4/extract/task' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "vlm"
}'
```

**CURL 请求示例（适用于 html 文件）：**

```
curl --location --request POST 'https://mineru.net/api/v4/extract/task' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "url": "https://****",
    "model_version": "MinerU-HTML"
}'
```

**请求体参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th><nobr><b>是否必选</b></nobr></th><th>示例</th><th>描述</th></tr></thead><tbody><tr><td>url</td><td>string</td><td>是</td><td><a href="https://cdn-mineru.openxlab.org.cn/demo/example.pdf">https://cdn-mineru.openxlab.org.cn/demo/example.pdf</a></td><td>文件 URL，支持. pdf、.doc、.docx、.ppt、.pptx、.xls、.xlsx、图片（png/jpg/jpeg/jp2/webp/gif/bmp）、.html 多种格式</td></tr><tr><td>is_ocr</td><td>bool</td><td>否</td><td>false</td><td>是否启动 ocr 功能，默认 false，仅对 pipeline、vlm 模型有效</td></tr><tr><td>enable_formula</td><td>bool</td><td>否</td><td>true</td><td>是否开启公式识别，默认 true，仅对 pipeline、vlm 模型有效。特别注意的是：对于 vlm 模型，这个参数指只会影响行内公式的解析</td></tr><tr><td>enable_table</td><td>bool</td><td>否</td><td>true</td><td>是否开启表格识别，默认 true，仅对 pipeline、vlm 模型有效</td></tr><tr><td>language</td><td>string</td><td>否</td><td>ch</td><td>指定文档语言，默认 <code node="[object Object]">ch</code>。可选值见 <a href="#language-%E5%8F%96%E5%80%BC%E5%8F%82%E8%80%83">language 取值参考</a>。仅对 pipeline、vlm 模型有效</td></tr><tr><td>data_id</td><td>string</td><td>否</td><td>abc**</td><td>解析对象对应的数据 ID。由大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.）组成，不超过 128 个字符，可以用于唯一标识您的业务数据。</td></tr><tr><td>callback</td><td>string</td><td>否</td><td><a href="http://127.0.0.1/callback">http://127.0.0.1/callback</a></td><td>解析结果回调通知您的 URL，支持使用 HTTP 和 HTTPS 协议的地址。该字段为空时，您必须定时轮询解析结果。callback 接口必须支持 POST 方法、UTF-8 编码、Content-Type:application/json 传输数据，以及参数 checksum 和 content。解析接口按照以下规则和格式设置 checksum 和 content，调用您的 callback 接口返回检测结果。<br>checksum：字符串格式，由用户 uid + seed + content 拼成字符串，通过 SHA256 算法生成。用户 UID，可在个人中心查询。为防篡改，您可以在获取到推送结果时，按上述算法生成字符串，与 checksum 做一次校验。<br>content：JSON 字符串格式，请自行解析反转成 JSON 对象。关于 content 结果的示例，请参见任务查询结果的返回示例，对应任务查询结果的 data 部分。<br>说明: 您的服务端 callback 接口收到 Mineru 解析服务推送的结果后，如果返回的 HTTP 状态码为 200，则表示接收成功，其他的 HTTP 状态码均视为接收失败。接收失败时，mineru 将最多重复推送 5 次检测结果，直到接收成功。重复推送 5 次后仍未接收成功，则不再推送，建议您检查 callback 接口的状态。</td></tr><tr><td>seed</td><td>string</td><td>否</td><td>abc**</td><td>随机字符串，该值用于回调通知请求中的签名。由英文字母、数字、下划线（_）组成，不超过 64 个字符，由您自定义。用于在接收到内容安全的回调通知时校验请求由 Mineru 解析服务发起。<br>说明：当使用 callback 时，该字段必须提供。</td></tr><tr><td>extra_formats</td><td>[string]</td><td>否</td><td>["docx","html"]</td><td>markdown、json 为默认导出格式，无须设置，该参数仅支持 docx、html、latex 三种格式中的一个或多个。对源文件为 html 的文件无效。</td></tr><tr><td>page_ranges</td><td>string</td><td>否</td><td>1-200</td><td>指定页码范围，格式为逗号分隔的字符串。例如："2,4-6"：表示选取第 2 页、第 4 页至第 6 页（包含 4 和 6，结果为 [2,4,5,6]）；"2--2"：表示从第 2 页一直选取到倒数第二页（其中 "-2" 表示倒数第二页）。</td></tr><tr><td>model_version</td><td>string</td><td>否</td><td>vlm</td><td>mineru 模型版本，三个选项: pipeline、vlm、MinerU-HTML，默认 pipeline。如果解析的是 HTML 文件，model_version 需明确指定为 MinerU-HTML，如果是非 HTML 文件，可选择 pipeline 或 vlm</td></tr><tr><td>no_cache</td><td>bool</td><td>否</td><td>false</td><td>是否绕过缓存，默认 false。我们的 API 服务器会将 URL 内容缓存一段时间，设置为 true 可忽略缓存结果，从 URL 获取最新内容。</td></tr><tr><td>cache_tolerance</td><td>int</td><td>否</td><td>900</td><td>缓存容忍时间（秒），默认 900（15 分钟）。 可容忍的 URL 内容缓存有效时间，超出该时间的缓存不会被使用。当 no_cache 为 false 时有效</td></tr></tbody></table>

**响应参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.task_id</td><td>string</td><td>a90e6ab6-44f3-4554-b459-b62fe4c6b436</td><td>提取任务 id，可用于查询任务结果</td></tr></tbody></table>

**响应示例**

```
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b4***"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

### [](#获取任务结果)获取任务结果

**接口说明**

通过 task_id 查询提取任务目前的进度，任务处理完成后，接口会响应对应的提取详情。

**Python 请求示例**

```
import requests

token = "官网申请的api token"
task_id = "上一步创建任务返回的 task_id"
url = f"https://mineru.net/api/v4/extract/task/{task_id}"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

res = requests.get(url, headers=header)
print(res.status_code)
print(res.json())
print(res.json()["data"])
```

**CURL 请求示例**

```
curl --location --request GET 'https://mineru.net/api/v4/extract/task/{task_id}' \
--header 'Authorization: Bearer *****' \
--header 'Accept: */*'
```

**响应参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.task_id</td><td>string</td><td>abc**</td><td>任务 ID</td></tr><tr><td>data.data_id</td><td>string</td><td>abc**</td><td>解析对象对应的数据 ID。<br>说明：如果在解析请求参数中传入了 data_id，则此处返回对应的 data_id。</td></tr><tr><td>data.state</td><td>string</td><td>done</td><td>任务处理状态，完成: done，pending: 排队中，running: 正在解析，failed：解析失败，converting：格式转换中</td></tr><tr><td>data.full_zip_url</td><td>string</td><td><a href="https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip">https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip</a></td><td>文件解析结果压缩包。非 html 文件解析结果详细说明请参考：<a href="https://opendatalab.github.io/MinerU/reference/output_files/">https://opendatalab.github.io/MinerU/reference/output_files/</a> ，其中 layout.json 对应中间处理结果 (middle.json), **_model.json 对应模型推理结果 (model.json)，**_content_list.json 对应内容列表 (content_list.json)，full.md 为 MarkDown 解析结果。html 文件解析结果略有不同：full.md 为 MarkDown 解析结果, main.html 为提取后正文 html</td></tr><tr><td>data.err_msg</td><td>string</td><td>文件格式不支持，请上传符合要求的文件类型</td><td>解析失败原因，当 state=failed 时有效</td></tr><tr><td>data.extract_progress.extracted_pages</td><td>int</td><td>1</td><td>文档已解析页数，当 state=running 时有效</td></tr><tr><td>data.extract_progress.start_time</td><td>string</td><td>2025-01-20 11:43:20</td><td>文档解析开始时间，当 state=running 时有效</td></tr><tr><td>data.extract_progress.total_pages</td><td>int</td><td>2</td><td>文档总页数，当 state=running 时有效</td></tr></tbody></table>

**响应示例**

```
{
  "code": 0,
  "data": {
    "task_id": "47726b6e-46ca-4bb9-******",
    "state": "running",
    "err_msg": "",
    "extract_progress": {
      "extracted_pages": 1,
      "total_pages": 2,
      "start_time": "2025-01-20 11:43:20"
    }
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

```
{
  "code": 0,
  "data": {
    "task_id": "47726b6e-46ca-4bb9-******",
    "state": "done",
    "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip",
    "err_msg": ""
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

[](#2批量文件解析)2. 批量文件解析
---------------------

### [](#本地文件批量上传解析)本地文件批量上传解析

**接口说明**

适用于本地文件上传解析的场景，可通过此接口批量申请文件上传链接，上传文件后，系统会自动提交解析任务 注意：

*   申请的文件上传链接有效期为 24 小时，请在有效期内完成文件上传
*   上传文件时，无须设置 Content-Type 请求头
*   文件上传完成后，无须调用提交解析任务接口。系统会自动扫描已上传完成文件自动提交解析任务
*   单次申请链接不能超过 50 个
*   header 头中需要包含 Authorization 字段，格式为 Bearer + 空格 + Token

**Python 请求示例（适用于 pdf、doc、ppt、excel、图片文件）：**

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/file-urls/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"name":"demo.pdf", "data_id": "abcd"}
    ],
    "model_version":"vlm"
}
file_path = ["demo.pdf"]
try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]
            print('batch_id:{},urls:{}'.format(batch_id, urls))
            for i in range(0, len(urls)):
                with open(file_path[i], 'rb') as f:
                    res_upload = requests.put(urls[i], data=f)
                    if res_upload.status_code == 200:
                        print(f"{urls[i]} upload success")
                    else:
                        print(f"{urls[i]} upload failed")
        else:
            print('apply upload url failed,reason:{}'.format(result["msg"]))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)
```

**Python 请求示例（适用于 html 文件）：**

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/file-urls/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"name":"demo.html", "data_id": "abcd"}
    ],
    "model_version":"MinerU-HTML"
}
file_path = ["demo.html"]
try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]
            print('batch_id:{},urls:{}'.format(batch_id, urls))
            for i in range(0, len(urls)):
                with open(file_path[i], 'rb') as f:
                    res_upload = requests.put(urls[i], data=f)
                    if res_upload.status_code == 200:
                        print(f"{urls[i]} upload success")
                    else:
                        print(f"{urls[i]} upload failed")
        else:
            print('apply upload url failed,reason:{}'.format(result["msg"]))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)
```

**CURL 请求示例（适用于 pdf、doc、ppt、excel、图片文件）：**

```
curl --location --request POST 'https://mineru.net/api/v4/file-urls/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"name":"demo.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}'
```

**CURL 请求示例（适用于 html 文件）：**

```
curl --location --request POST 'https://mineru.net/api/v4/file-urls/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"name":"demo.html", "data_id": "abcd"}
    ],
    "model_version": "MinerU-HTML"
}'
```

**CURL 文件上传示例：**

```
curl -X PUT -T /path/to/your/file.pdf 'https://****'
```

**请求体参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th><nobr><b>是否必选</b></nobr></th><th>示例</th><th>描述</th></tr></thead><tbody><tr><td>enable_formula</td><td>bool</td><td>否</td><td>true</td><td>是否开启公式识别，默认 true，仅对 pipeline、vlm 模型有效。特别注意的是：对于 vlm 模型，这个参数指只会影响行内公式的解析</td></tr><tr><td>enable_table</td><td>bool</td><td>否</td><td>true</td><td>是否开启表格识别，默认 true，仅对 pipeline、vlm 模型有效</td></tr><tr><td>language</td><td>string</td><td>否</td><td>ch</td><td>指定文档语言，默认 <code node="[object Object]">ch</code>。可选值见 <a href="#language-%E5%8F%96%E5%80%BC%E5%8F%82%E8%80%83">language 取值参考</a>。仅对 pipeline、vlm 模型有效</td></tr><tr><td>file.‌name</td><td>string</td><td>是</td><td>demo.pdf</td><td>文件名，支持. pdf、.doc、.docx、.ppt、.pptx、.xls、.xlsx、图片（png/jpg/jpeg/jp2/webp/gif/bmp）、.html 多种格式，我们强烈建议文件名带上正确的后缀名</td></tr><tr><td>file.is_ocr</td><td>bool</td><td>否</td><td>true</td><td>是否启动 ocr 功能，默认 false，仅对 pipeline、vlm 模型有效</td></tr><tr><td>file.data_id</td><td>string</td><td>否</td><td>abc**</td><td>解析对象对应的数据 ID。由大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.）组成，不超过 128 个字符，可以用于唯一标识您的业务数据。</td></tr><tr><td>file.page_ranges</td><td>string</td><td>否</td><td>1-200</td><td>指定页码范围，格式为逗号分隔的字符串。例如："2,4-6"：表示选取第 2 页、第 4 页至第 6 页（包含 4 和 6，结果为 [2,4,5,6]）；"2--2"：表示从第 2 页一直选取到倒数第二页（其中 "-2" 表示倒数第二页）。</td></tr><tr><td>callback</td><td>string</td><td>否</td><td><a href="http://127.0.0.1/callback">http://127.0.0.1/callback</a></td><td>解析结果回调通知您的 URL，支持使用 HTTP 和 HTTPS 协议的地址。该字段为空时，您必须定时轮询解析结果。callback 接口必须支持 POST 方法、UTF-8 编码、Content-Type:application/json 传输数据，以及参数 checksum 和 content。解析接口按照以下规则和格式设置 checksum 和 content，调用您的 callback 接口返回检测结果。<br>checksum：字符串格式，由用户 uid + seed + content 拼成字符串，通过 SHA256 算法生成。用户 UID，可在个人中心查询。为防篡改，您可以在获取到推送结果时，按上述算法生成字符串，与 checksum 做一次校验。<br>content：JSON 字符串格式，请自行解析反转成 JSON 对象。关于 content 结果的示例，请参见任务查询结果的返回示例，对应任务查询结果的 data 部分。<br>说明: 您的服务端 callback 接口收到 Mineru 解析服务推送的结果后，如果返回的 HTTP 状态码为 200，则表示接收成功，其他的 HTTP 状态码均视为接收失败。接收失败时，mineru 将最多重复推送 5 次检测结果，直到接收成功。重复推送 5 次后仍未接收成功，则不再推送，建议您检查 callback 接口的状态。</td></tr><tr><td>seed</td><td>string</td><td>否</td><td>abc**</td><td>随机字符串，该值用于回调通知请求中的签名。由英文字母、数字、下划线（_）组成，不超过 64 个字符。由您自定义，用于在接收到内容安全的回调通知时校验请求由 Mineru 解析服务发起。<br>说明: 当使用 callback 时，该字段必须提供。</td></tr><tr><td>extra_formats</td><td>[string]</td><td>否</td><td>["docx","html"]</td><td>markdown、json 为默认导出格式，无须设置，该参数仅支持 docx、html、latex 三种格式中的一个或多个。对源文件为 html 的文件无效。</td></tr><tr><td>model_version</td><td>string</td><td>否</td><td>vlm</td><td>mineru 模型版本，三个选项: pipeline、vlm、MinerU-HTML，默认 pipeline。如果解析的是 HTML 文件，model_version 需明确指定为 MinerU-HTML，如果是非 HTML 文件，可选择 pipeline 或 vlm</td></tr></tbody></table>

**响应参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功： 0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.batch_id</td><td>string</td><td>2bb2f0ec-a336-4a0a-b61a-****</td><td>批量提取任务 id，可用于批量查询解析结果</td></tr><tr><td>data.file_urls</td><td>[string]</td><td>["<a href="https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/***">https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/***</a>"]</td><td>文件上传链接</td></tr></tbody></table>

**响应示例**

```
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87",
    "file_urls": ["https://***"]
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

### [](#url-批量上传解析)url 批量上传解析

**接口说明**

适用于通过 API 批量创建提取任务的场景 注意：

*   单次申请链接不能超过 50 个
*   文件大小不能超过 200MB, 文件页数不超出 200 页
*   因网络限制，github、aws 等国外 URL 会请求超时
*   header 头中需要包含 Authorization 字段，格式为 Bearer + 空格 + Token

**Python 请求示例（适用于 pdf、doc、ppt、excel、图片文件）：**

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"url":"https://cdn-mineru.openxlab.org.cn/demo/example.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}
try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            print('batch_id:{}'.format(batch_id))
        else:
            print('submit task failed,reason:{}'.format(result["msg"]))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)
```

**Python 请求示例（适用于 html 文件）：**

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"url":"https://***", "data_id": "abcd"}
    ],
    "model_version": "MinerU-HTML"
}
try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            print('batch_id:{}'.format(batch_id))
        else:
            print('submit task failed,reason:{}'.format(result["msg"]))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)
```

**CURL 请求示例（适用于 pdf、doc、ppt、excel、图片文件）：**

```
curl --location --request POST 'https://mineru.net/api/v4/extract/task/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"url":"https://cdn-mineru.openxlab.org.cn/demo/example.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}'
```

**CURL 请求示例（适用于 html 文件）：**

```
curl --location --request POST 'https://mineru.net/api/v4/extract/task/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"url":"https://***", "data_id": "abcd"}
    ],
    "model_version": "MinerU-HTML"
}'
```

**请求体参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th><nobr><b>是否必选</b></nobr></th><th>示例</th><th>描述</th></tr></thead><tbody><tr><td>enable_formula</td><td>bool</td><td>否</td><td>true</td><td>是否开启公式识别，默认 true，仅对 pipeline、vlm 模型有效。特别注意的是：对于 vlm 模型，这个参数指只会影响行内公式的解析</td></tr><tr><td>enable_table</td><td>bool</td><td>否</td><td>true</td><td>是否开启表格识别，默认 true，仅对 pipeline、vlm 模型有效</td></tr><tr><td>language</td><td>string</td><td>否</td><td>ch</td><td>指定文档语言，默认 <code node="[object Object]">ch</code>。可选值见 <a href="#language-%E5%8F%96%E5%80%BC%E5%8F%82%E8%80%83">language 取值参考</a>。仅对 pipeline、vlm 模型有效</td></tr><tr><td>file.url</td><td>string</td><td>是</td><td><a href="https://cdn-mineru.openxlab.org.cn/demo/example.pdf">demo.pdf</a></td><td>文件链接，支持. pdf、.doc、.docx、.ppt、.pptx、.xls、.xlsx、图片（png/jpg/jpeg/jp2/webp/gif/bmp、.html 多种格式</td></tr><tr><td>file.is_ocr</td><td>bool</td><td>否</td><td>true</td><td>是否启动 ocr 功能，默认 false，仅对 pipeline、vlm 模型有效</td></tr><tr><td>file.data_id</td><td>string</td><td>否</td><td>abc**</td><td>解析对象对应的数据 ID。由大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.）组成，不超过 128 个字符，可以用于唯一标识您的业务数据。</td></tr><tr><td>file.page_ranges</td><td>string</td><td>否</td><td>1-200</td><td>指定页码范围，格式为逗号分隔的字符串。例如："2,4-6"：表示选取第 2 页、第 4 页至第 6 页（包含 4 和 6，结果为 [2,4,5,6]）；"2--2"：表示从第 2 页一直选取到倒数第二页（其中 "-2" 表示倒数第二页）。</td></tr><tr><td>callback</td><td>string</td><td>否</td><td><a href="http://127.0.0.1/callback">http://127.0.0.1/callback</a></td><td>解析结果回调通知您的 URL，支持使用 HTTP 和 HTTPS 协议的地址。该字段为空时，您必须定时轮询解析结果。callback 接口必须支持 POST 方法、UTF-8 编码、Content-Type:application/json 传输数据，以及参数 checksum 和 content。解析接口按照以下规则和格式设置 checksum 和 content，调用您的 callback 接口返回检测结果。<br>checksum：字符串格式，由用户 uid + seed + content 拼成字符串，通过 SHA256 算法生成。用户 UID，可在个人中心查询。为防篡改，您可以在获取到推送结果时，按上述算法生成字符串，与 checksum 做一次校验。<br>content：JSON 字符串格式，请自行解析反转成 JSON 对象。关于 content 结果的示例，请参见任务查询结果的返回示例，对应任务查询结果的 data 部分。<br>说明: 您的服务端 callback 接口收到 Mineru 解析服务推送的结果后，如果返回的 HTTP 状态码为 200，则表示接收成功，其他的 HTTP 状态码均视为接收失败。接收失败时，mineru 将最多重复推送 5 次检测结果，直到接收成功。重复推送 5 次后仍未接收成功，则不再推送，建议您检查 callback 接口的状态。</td></tr><tr><td>seed</td><td>string</td><td>否</td><td>abc**</td><td>随机字符串，该值用于回调通知请求中的签名。由英文字母、数字、下划线（_）组成，不超过 64 个字符。由您自定义，用于在接收到内容安全的回调通知时校验请求由 Mineru 解析服务发起。<br>说明：当使用 callback 时，该字段必须提供。</td></tr><tr><td>extra_formats</td><td>[string]</td><td>否</td><td>["docx","html"]</td><td>markdown、json 为默认导出格式，无须设置，该参数仅支持 docx、html、latex 三种格式中的一个或多个。对源文件为 html 的文件无效。</td></tr><tr><td>model_version</td><td>string</td><td>否</td><td>vlm</td><td>mineru 模型版本，三个选项: pipeline、vlm、MinerU-HTML，默认 pipeline。如果解析的是 HTML 文件，model_version 需明确指定为 MinerU-HTML，如果是非 HTML 文件，可选择 pipeline 或 vlm</td></tr><tr><td>no_cache</td><td>bool</td><td>否</td><td>false</td><td>是否绕过缓存，默认 false。我们的 API 服务器会将 URL 内容缓存一段时间，设置为 true 可忽略缓存结果，从 URL 获取最新内容。</td></tr><tr><td>cache_tolerance</td><td>int</td><td>否</td><td>900</td><td>缓存容忍时间（秒），默认 900（15 分钟）。 可容忍的 URL 内容缓存有效时间，超出该时间的缓存不会被使用。当 no_cache 为 false 时有效</td></tr></tbody></table>

**请求体示例**

```
{
  "files": [
    {
      "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
      "data_id": "abcd"
    }
  ],
  "model_version": "vlm"
}
```

**响应参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.batch_id</td><td>string</td><td>2bb2f0ec-a336-4a0a-b61a-****</td><td>批量提取任务 id，可用于批量查询解析结果</td></tr></tbody></table>

**响应示例**

```
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

### [](#批量获取任务结果)批量获取任务结果

**接口说明**

通过 batch_id 批量查询提取任务的进度。

**Python 请求示例**

```
import requests

token = "官网申请的api token"
batch_id = "上一步批量提交返回的 batch_id"
url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

res = requests.get(url, headers=header)
print(res.status_code)
print(res.json())
print(res.json()["data"])
```

**CURL 请求示例**

```
curl --location --request GET 'https://mineru.net/api/v4/extract-results/batch/{batch_id}' \
--header 'Authorization: Bearer *****' \
--header 'Accept: */*'
```

**响应参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.batch_id</td><td>string</td><td>2bb2f0ec-a336-4a0a-b61a-241afaf9cc87</td><td>batch_id</td></tr><tr><td>data.extract_result.file_name</td><td>string</td><td>demo.pdf</td><td>文件名</td></tr><tr><td>data.extract_result.state</td><td>string</td><td>done</td><td>任务处理状态，完成: done，waiting-file: 等待文件上传排队提交解析任务中，pending: 排队中，running: 正在解析，failed：解析失败，converting：格式转换中</td></tr><tr><td>data.extract_result.full_zip_url</td><td>string</td><td><a href="https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip">https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip</a></td><td>文件解析结果压缩包。非 html 文件解析结果详细说明请参考：<a href="https://opendatalab.github.io/MinerU/reference/output_files/">https://opendatalab.github.io/MinerU/reference/output_files/</a> ，其中 layout.json 对应中间处理结果 (middle.json), **_model.json 对应模型推理结果 (model.json)，**_content_list.json 对应内容列表 (content_list.json)，full.md 为 MarkDown 解析结果。html 文件解析结果略有不同：full.md 为 MarkDown 解析结果, main.html 为提取后正文 html</td></tr><tr><td>data.extract_result.err_msg</td><td>string</td><td>文件格式不支持，请上传符合要求的文件类型</td><td>解析失败原因，当 state=failed 时，有效</td></tr><tr><td>data.extract_result.data_id</td><td>string</td><td>abc**</td><td>解析对象对应的数据 ID。<br>说明：如果在解析请求参数中传入了 data_id，则此处返回对应的 data_id。</td></tr><tr><td>data.extract_result.extract_progress.extracted_pages</td><td>int</td><td>1</td><td>文档已解析页数，当 state=running 时有效</td></tr><tr><td>data.extract_result.extract_progress.start_time</td><td>string</td><td>2025-01-20 11:43:20</td><td>文档解析开始时间，当 state=running 时有效</td></tr><tr><td>data.extract_result.extract_progress.total_pages</td><td>int</td><td>2</td><td>文档总页数，当 state=running 时有效</td></tr></tbody></table>

**响应示例**

```
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87",
    "extract_result": [
      {
        "file_name": "example.pdf",
        "state": "done",
        "err_msg": "",
        "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip"
      },
      {
        "file_name": "demo.pdf",
        "state": "running",
        "err_msg": "",
        "extract_progress": {
          "extracted_pages": 1,
          "total_pages": 2,
          "start_time": "2025-01-20 11:43:20"
        }
      }
    ]
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

### [](#常见错误码)常见错误码

<table node="[object Object]"><thead><tr><th>错误码</th><th>说明</th><th>解决建议</th></tr></thead><tbody><tr><td>A0202</td><td>Token 错误</td><td>检查 Token 是否正确，请检查是否有 Bearer 前缀 或者更换新 Token</td></tr><tr><td>A0211</td><td>Token 过期</td><td>更换新 Token</td></tr><tr><td>-500</td><td>传参错误</td><td>请确保参数类型及 Content-Type 正确</td></tr><tr><td>-10001</td><td>服务异常</td><td>请稍后再试</td></tr><tr><td>-10002</td><td>请求参数错误</td><td>检查请求参数格式</td></tr><tr><td>-60001</td><td>生成上传 URL 失败，请稍后再试</td><td>请稍后再试</td></tr><tr><td>-60002</td><td>获取匹配的文件格式失败</td><td>检测文件类型失败，请求的文件名及链接中带有正确的后缀名，且文件为 pdf,doc,docx,ppt,pptx,xls,xlsx,png,jp(e)g 中的一种</td></tr><tr><td>-60003</td><td>文件读取失败</td><td>请检查文件是否损坏并重新上传</td></tr><tr><td>-60004</td><td>空文件</td><td>请上传有效文件</td></tr><tr><td>-60005</td><td>文件大小超出限制</td><td>检查文件大小，最大支持 200MB</td></tr><tr><td>-60006</td><td>文件页数超过限制</td><td>请拆分文件后重试</td></tr><tr><td>-60007</td><td>模型服务暂时不可用</td><td>请稍后重试或联系技术支持</td></tr><tr><td>-60008</td><td>文件读取超时</td><td>检查 URL 可访问</td></tr><tr><td>-60009</td><td>任务提交队列已满</td><td>请稍后再试</td></tr><tr><td>-60010</td><td>解析失败</td><td>请稍后再试</td></tr><tr><td>-60011</td><td>获取有效文件失败</td><td>请确保文件已上传</td></tr><tr><td>-60012</td><td>找不到任务</td><td>请确保 task_id 有效且未删除</td></tr><tr><td>-60013</td><td>没有权限访问该任务</td><td>只能访问自己提交的任务</td></tr><tr><td>-60014</td><td>删除运行中的任务</td><td>运行中的任务暂不支持删除</td></tr><tr><td>-60015</td><td>文件转换失败</td><td>可以手动转为 pdf 再上传</td></tr><tr><td>-60016</td><td>文件转换失败</td><td>文件转换为指定格式失败，可以尝试其他格式导出或重试</td></tr><tr><td>-60017</td><td>重试次数达到上限</td><td>等后续模型升级后重试</td></tr><tr><td>-60018</td><td>每日解析任务数量已达上限</td><td>明日再来</td></tr><tr><td>-60019</td><td>html 文件解析额度不足</td><td>明日再来</td></tr><tr><td>-60020</td><td>文件拆分失败</td><td>请稍后重试</td></tr><tr><td>-60021</td><td>读取文件页数失败</td><td>请稍后重试</td></tr><tr><td>-60022</td><td>网页读取失败</td><td>可能因网络问题或者限频导致读取失败，请稍后重试</td></tr></tbody></table>

[](#-agent-轻量解析-api)⚡ Agent 轻量解析 API
====================================

> 免登录，无需 Token，IP 限频防滥用。专为 OpenClaw 等 AI Agent 场景设计，仅输出 Markdown，免登录零门槛。

[](#概述-1)概述
-----------

Agent 轻量解析接口专为 OpenClaw 等 AI Agent 场景设计，提供快速、免登录的文档解析能力。

**核心特性：**

*   **无需登录**：通过 IP 限频防滥用，无需申请 Token
*   **轻量快速**：PDF、图片使用 pipeline 轻量模型，禁用表格 / 公式识别，追求最快解析速度; Word、PPT 使用 Office 原生 API 解析
*   **统一输出**：仅输出 Markdown 格式，返回 CDN 链接
*   **双模式提交**：URL 解析和文件上传为独立接口，文件上传采用签名上传模式

**文件限制：**

<table node="[object Object]"><thead><tr><th>限制项</th><th>限制值</th></tr></thead><tbody><tr><td>文件大小上限</td><td>10 MB</td></tr><tr><td>文件页数上限</td><td>20 页</td></tr><tr><td>支持文件类型</td><td>PDF、图片（png/jpg/jpeg/jp2/webp/gif/bmp）、Docx、PPTx、Xlsx</td></tr></tbody></table>

**IP 限频：**

*   每 IP 每分钟提交请求数有限制
*   超出限制将返回 HTTP 429 状态码

[](#1-url-解析接口)1. URL 解析接口
--------------------------

**接口说明**

提交一个远程文件 URL 进行解析。后端自动下载并解析文件。

接口为异步返回模式，提交成功后返回 `task_id`，需通过查询接口轮询结果。

**请求地址**

```
POST https://mineru.net/api/v1/agent/parse/url
```

**请求体参数说明（JSON）**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th><nobr><b>是否必选</b></nobr></th><th>说明</th></tr></thead><tbody><tr><td>url</td><td>string</td><td>必填</td><td>远程文件 URL，支持 PDF、图片、Doc/Docx、PPT/PPTx、Xlsx 格式。不支持 HTML。</td></tr><tr><td>file_name</td><td>string</td><td>可选</td><td>文件名（含扩展名），用于判断文件类型。若不提供则从 URL 自动解析。</td></tr><tr><td>language</td><td>string</td><td>可选</td><td>解析语言，影响 OCR 识别效果。默认 <code node="[object Object]">ch</code>。可选值见 <a href="#language-%E5%8F%96%E5%80%BC%E5%8F%82%E8%80%83">language 取值参考</a>。仅对 PDF 文件生效</td></tr><tr><td>enable_table</td><td>bool</td><td>可选</td><td>是否开启表格识别。默认 <code node="[object Object]">true</code>。仅对 PDF 文件生效</td></tr><tr><td>is_ocr</td><td>bool</td><td>可选</td><td>是否开启 OCR。默认 <code node="[object Object]">false</code>。仅对 PDF 文件生效</td></tr><tr><td>enable_formula</td><td>bool</td><td>可选</td><td>是否开启公式识别。默认 <code node="[object Object]">true</code>。仅对 PDF 文件生效</td></tr><tr><td>page_range</td><td>string</td><td>可选</td><td>页码范围，仅对 PDF 有效。支持 <code node="[object Object]">from-to</code>（如 <code node="[object Object]">1-10</code>）或单个页码（如 <code node="[object Object]">5</code>），不支持逗号分隔的复杂格式。</td></tr></tbody></table>

**注意：**

*   无需 Authorization 请求头
*   请求体为 JSON 格式（`Content-Type: application/json`），不支持 multipart/form-data

**Python 请求示例**

```
import requests

url = "https://mineru.net/api/v1/agent/parse/url"

data = {
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "language": "ch",
    "page_range": "1-10",
    "enable_table": True,
    "is_ocr": False,
    "enable_formula": True
}

res = requests.post(url, json=data)
print(res.json())
```

**CURL 请求示例**

```
curl --location --request POST 'https://mineru.net/api/v1/agent/parse/url' \
--header 'Content-Type: application/json' \
--data-raw '{
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "language": "ch",
    "page_range": "1-10",
    "enable_table": true,
    "is_ocr": false,
    "enable_formula": true
}'
```

**响应参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.task_id</td><td>string</td><td>a90e6ab6-44f3-4554-b459-b62fe4c6b43605</td><td>解析任务 ID，用于查询任务结果。</td></tr></tbody></table>

**响应示例**

```
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

[](#2-本地文件上传接口签名上传)2. 本地文件上传接口（签名上传）
------------------------------------

**接口说明**

提交一个文件上传解析任务。接口采用**签名上传模式**：

1.  调用本接口，传入文件名等参数，获取 `task_id`、OSS 签名上传 URL（`file_url`）
2.  客户端使用 `PUT` 方法将文件直接上传到 `file_url`
3.  上传完成后，后端自动检测并开始解析
4.  通过查询接口轮询解析结果

**请求地址**

```
POST https://mineru.net/api/v1/agent/parse/file
```

**请求体参数说明（JSON）**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th><nobr><b>是否必选</b></nobr></th><th>说明</th></tr></thead><tbody><tr><td>file_name</td><td>string</td><td>必填</td><td>文件名（含扩展名），用于判断文件类型。</td></tr><tr><td>language</td><td>string</td><td>可选</td><td>解析语言，影响 OCR 识别效果。默认 <code node="[object Object]">ch</code>。可选值见 <a href="#language-%E5%8F%96%E5%80%BC%E5%8F%82%E8%80%83">language 取值参考</a>。仅对 PDF 文件生效</td></tr><tr><td>enable_table</td><td>bool</td><td>可选</td><td>是否开启表格识别。默认 <code node="[object Object]">true</code>。仅对 PDF 文件生效</td></tr><tr><td>is_ocr</td><td>bool</td><td>可选</td><td>是否开启 OCR。默认 <code node="[object Object]">false</code>。仅对 PDF 文件生效</td></tr><tr><td>enable_formula</td><td>bool</td><td>可选</td><td>是否开启公式识别。默认 <code node="[object Object]">true</code>。仅对 PDF 文件生效</td></tr><tr><td>page_range</td><td>string</td><td>可选</td><td>页码范围，仅对 PDF 有效。支持 <code node="[object Object]">from-to</code>（如 <code node="[object Object]">1-10</code>）或单个页码（如 <code node="[object Object]">5</code>），不支持逗号分隔的复杂格式。</td></tr></tbody></table>

**注意：**

*   无需 Authorization 请求头
*   请求体为 JSON 格式（`application/json`）
*   不支持批量上传，每次请求只能上传一个文件

**响应参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.task_id</td><td>string</td><td>a90e6ab6-44f3-4554-b459-b62fe4c6b43605</td><td>解析任务 ID，用于查询任务结果。</td></tr><tr><td>data.file_url</td><td>string</td><td><a href="https://oss-mineru.../agent/a90e6ab6-...pdf">https://oss-mineru.../agent/a90e6ab6-...pdf</a></td><td>OSS 签名上传 URL，客户端 PUT 上传文件到此地址</td></tr></tbody></table>

**响应示例**

```
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605",
    "file_url": "https://oss-mineru.openxlab.org.cn/agent/a90e6ab6-...pdf?Expires=..."
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

**Python 请求示例（完整签名上传流程）**

```
import requests

# 第一步：获取签名上传 URL
api_url = "https://mineru.net/api/v1/agent/parse/file"
data = {
    "file_name": "document.pdf",
    "language": "ch",
    "page_range": "1-10",
    "enable_table": True,
    "is_ocr": False,
    "enable_formula": True
}

res = requests.post(api_url, json=data)
result = res.json()
task_id = result["data"]["task_id"]
file_url = result["data"]["file_url"]

print(f"任务已创建, task_id: {task_id}")

# 第二步：PUT 上传文件到 OSS
with open("document.pdf", "rb") as f:
    put_res = requests.put(file_url, data=f)
    print(f"文件上传状态: {put_res.status_code}")
```

**CURL 请求示例**

```
# 第一步：获取签名上传 URL
curl --location --request POST 'https://mineru.net/api/v1/agent/parse/file' \
--header 'Content-Type: application/json' \
--data-raw '{
    "file_name": "document.pdf",
    "language": "ch",
    "page_range": "1-10",
    "enable_table": true,
    "is_ocr": false,
    "enable_formula": true
}'

# 第二步：PUT 上传文件到返回的 file_url
curl --location --request PUT '<file_url>' \
--data-binary '@document.pdf'
```

[](#3-查询解析结果)3. 查询解析结果
----------------------

**接口说明**

通过 `task_id` 查询解析任务的状态和结果。任务处理完成后，响应中包含 Markdown 结果文件的 CDN 下载链接。

**请求地址**

```
GET https://mineru.net/api/v1/agent/parse/{task_id}
```

**Python 请求示例**

```
import requests

task_id = "a90e6ab6-44f3-4554-b459-b62fe4c6b43605"
url = f"https://mineru.net/api/v1/agent/parse/{task_id}"

res = requests.get(url)
print(res.json())
```

**CURL 请求示例**

```
curl --location --request GET 'https://mineru.net/api/v1/agent/parse/{task_id}'
```

**响应参数说明**

<table node="[object Object]"><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.task_id</td><td>string</td><td>a90e6ab6-...05</td><td>任务 ID（与提交时返回的一致）</td></tr><tr><td>data.state</td><td>string</td><td>done</td><td>任务状态：waiting-file（等待文件上传，仅文件上传模式）、uploading(文件下载中)、pending（排队中）、running（解析中）、done（完成）、failed（失败）</td></tr><tr><td>data.markdown_url</td><td>string</td><td><a href="https://cdn-mineru.../full.md">https://cdn-mineru.../full.md</a></td><td>Markdown 结果文件的 CDN 下载链接，当 state=done 时有效</td></tr><tr><td>data.err_msg</td><td>string</td><td>file page count exceeds lightweight API limit</td><td>错误信息，当 state=failed 时有效</td></tr><tr><td>data.err_code</td><td>int</td><td>-30003</td><td>错误码，当 state=failed 时有效。详见底部错误码表</td></tr></tbody></table>

**响应示例（等待文件上传 — 仅文件上传模式）**

```
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605",
    "state": "waiting-file"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

**响应示例（处理中）**

```
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605",
    "state": "running"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

**响应示例（完成）**

```
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605",
    "state": "done",
    "markdown_url": "https://cdn-mineru.openxlab.org.cn/pdf/a90e6ab6-.../full.md"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

**响应示例（失败）**

```
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605",
    "state": "failed",
    "err_code": -30003,
    "err_msg": "file page count exceeds lightweight API limit (50 pages), please use the standard API"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

[](#完整使用示例python)完整使用示例（Python）
-------------------------------

**URL 模式**

```
def parse_by_url(url, language="ch", page_range=None, enable_table=True, is_ocr=False, enable_formula=True):
    """通过 URL 提交文档解析任务并等待结果。"""
    # 1. 提交 URL 解析任务
    data = {"url": url, "language": language, "enable_table": enable_table, "is_ocr": is_ocr, "enable_formula": enable_formula}
    if page_range:
        data["page_range"] = page_range

    resp = requests.post(f"{BASE_URL}/parse/url", json=data)
    result = resp.json()
    if result["code"] != 0:
        print(f"提交失败: {result['msg']}")
        return None

    task_id = result["data"]["task_id"]
    print(f"任务已提交, task_id: {task_id}")

    # 2. 轮询等待结果
    return poll_result(task_id)


def poll_result(task_id, timeout=300, interval=3):
    """轮询查询解析结果。"""
    state_labels = {
        "uploading": "文件下载中",
        "pending": "排队中",
        "running": "解析中",
        "waiting-file": "等待文件上传",
    }
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/parse/{task_id}")
        result = resp.json()
        state = result["data"]["state"]
        elapsed = int(time.time() - start)

        if state == "done":
            markdown_url = result["data"]["markdown_url"]
            print(f"[{elapsed}s] 解析完成, Markdown 下载链接: {markdown_url}")
            md_resp = requests.get(markdown_url)
            return md_resp.text

        if state == "failed":
            print(f"[{elapsed}s] 解析失败: {result['data'].get('err_msg', '未知错误')}")
            return None

        print(f"[{elapsed}s] {state_labels.get(state, state)}...")
        time.sleep(interval)

    print(f"轮询超时 ({timeout}s)，请稍后手动查询 task_id: {task_id}")
    return None


# 使用示例
content = parse_by_url("https://cdn-mineru.openxlab.org.cn/demo/example.pdf")
```

**文件上传模式（签名上传）**

```
import requests
import time

BASE_URL = "https://mineru.net/api/v1/agent"

def parse_by_file(file_path, language="ch", page_range=None, enable_table=True, is_ocr=False, enable_formula=True):
    """通过文件上传提交文档解析任务并等待结果。"""
    file_name = file_path.split("/")[-1].split("\\")[-1]

    # 1. 获取签名上传 URL
    data = {"file_name": file_name, "language": language, "enable_table": enable_table, "is_ocr": is_ocr, "enable_formula": enable_formula}
    if page_range:
        data["page_range"] = page_range

    resp = requests.post(f"{BASE_URL}/parse/file", json=data)
    result = resp.json()
    if result["code"] != 0:
        print(f"获取上传链接失败: {result['msg']}")
        return None

    task_id = result["data"]["task_id"]
    file_url = result["data"]["file_url"]
    print(f"任务已创建, task_id: {task_id}")

    # 2. PUT 上传文件到 OSS
    with open(file_path, "rb") as f:
        put_resp = requests.put(file_url, data=f)
        if put_resp.status_code not in (200, 201):
            print(f"文件上传失败, HTTP {put_resp.status_code}")
            return None
    print("文件上传成功，等待解析...")

    # 3. 轮询等待结果
    return poll_result(task_id)


def poll_result(task_id, timeout=300, interval=3):
    """轮询查询解析结果。"""
    state_labels = {
        "pending": "排队中",
        "running": "解析中",
        "waiting-file": "等待文件上传",
    }
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/parse/{task_id}")
        result = resp.json()
        state = result["data"]["state"]
        elapsed = int(time.time() - start)

        if state == "done":
            markdown_url = result["data"]["markdown_url"]
            print(f"[{elapsed}s] 解析完成, Markdown 下载链接: {markdown_url}")
            md_resp = requests.get(markdown_url)
            return md_resp.text

        if state == "failed":
            print(f"[{elapsed}s] 解析失败: {result['data'].get('err_msg', '未知错误')}")
            return None

        print(f"[{elapsed}s] {state_labels.get(state, state)}...")
        time.sleep(interval)

    print(f"轮询超时 ({timeout}s)，请稍后手动查询 task_id: {task_id}")
    return None


# 使用示例
content = parse_by_file("./document.pdf")
```

[](#agent-专属错误码)Agent 专属错误码
---------------------------

<table node="[object Object]"><thead><tr><th>错误码</th><th>说明</th><th>Agent 应对策略</th></tr></thead><tbody><tr><td>-30001</td><td>文件大小超出轻量接口限制（10MB）</td><td>请使用标准 API 或拆分文件</td></tr><tr><td>-30002</td><td>轻量接口不支持该文件类型</td><td>请上传 PDF / 图片 / Doc/PPT/Excel</td></tr><tr><td>-30003</td><td>文件页数超出轻量接口限制</td><td>请使用标准 API 或指定 page_range</td></tr><tr><td>-30004</td><td>请求参数错误</td><td>检查必填参数是否缺失</td></tr></tbody></table>

[](#language-取值参考)language 取值参考
-------------------------------

`language` 字段建议按下表传入。默认值为 `ch`。

#### [](#standalone-language-packs)Standalone language packs

<table node="[object Object]"><thead><tr><th>Value</th><th>Included languages</th><th>说明</th></tr></thead><tbody><tr><td><code node="[object Object]">ch</code></td><td>Chinese, English, Chinese Traditional</td><td>中英文（默认值）</td></tr><tr><td><code node="[object Object]">ch_server</code></td><td>Chinese, English, Chinese Traditional, Japanese</td><td>繁体、手写体</td></tr><tr><td><code node="[object Object]">en</code></td><td>English</td><td>纯英文</td></tr><tr><td><code node="[object Object]">japan</code></td><td>Chinese, English, Chinese Traditional, Japanese</td><td>日文为主</td></tr><tr><td><code node="[object Object]">korean</code></td><td>Korean, English</td><td>韩文</td></tr><tr><td><code node="[object Object]">chinese_cht</code></td><td>Chinese, English, Chinese Traditional, Japanese</td><td>繁体中文为主</td></tr><tr><td><code node="[object Object]">ta</code></td><td>Tamil, English</td><td>泰米尔文</td></tr><tr><td><code node="[object Object]">te</code></td><td>Telugu, English</td><td>泰卢固文</td></tr><tr><td><code node="[object Object]">ka</code></td><td>Kannada</td><td>卡纳达文</td></tr><tr><td><code node="[object Object]">el</code></td><td>Greek, English</td><td>希腊文</td></tr><tr><td><code node="[object Object]">th</code></td><td>Thai, English</td><td>泰文</td></tr></tbody></table>

#### [](#language-family-packs)Language family packs

<table node="[object Object]"><thead><tr><th>Value</th><th>Script/Family</th><th>Included languages</th></tr></thead><tbody><tr><td><code node="[object Object]">latin</code></td><td>Latin script (拉丁语系)</td><td>French, German, Afrikaans, Italian, Spanish, Bosnian, Portuguese, Czech, Welsh, Danish, Estonian, Irish, Croatian, Uzbek, Hungarian, Serbian (Latin), Indonesian, Occitan, Icelandic, Lithuanian, Maori, Malay, Dutch, Norwegian, Polish, Slovak, Slovenian, Albanian, Swedish, Swahili, Tagalog, Turkish, Latin, Azerbaijani, Kurdish, Latvian, Maltese, Pali, Romanian, Vietnamese, Finnish, Basque, Galician, Luxembourgish, Romansh, Catalan, Quechua</td></tr><tr><td><code node="[object Object]">arabic</code></td><td>Arabic script (阿拉伯语系)</td><td>Arabic, Persian, Uyghur, Urdu, Pashto, Kurdish, Sindhi, Balochi, English</td></tr><tr><td><code node="[object Object]">cyrillic</code></td><td>Cyrillic script (西里尔语系)</td><td>Russian, Belarusian, Ukrainian, Serbian (Cyrillic), Bulgarian, Mongolian, Abkhazian, Adyghe, Kabardian, Avar, Dargin, Ingush, Chechen, Lak, Lezgin, Tabasaran, Kazakh, Kyrgyz, Tajik, Macedonian, Tatar, Chuvash, Bashkir, Malian, Moldovan, Udmurt, Komi, Ossetian, Buryat, Kalmyk, Tuvan, Sakha, Karakalpak, English</td></tr><tr><td><code node="[object Object]">east_slavic</code></td><td>East Slavic (东斯拉夫语系)</td><td>Russian, Belarusian, Ukrainian, English</td></tr><tr><td><code node="[object Object]">devanagari</code></td><td>Devanagari script (天城文语系)</td><td>Hindi, Marathi, Nepali, Bihari, Maithili, Angika, Bhojpuri, Magahi, Santali, Newari, Konkani, Sanskrit, Haryanvi, English</td></tr></tbody></table>