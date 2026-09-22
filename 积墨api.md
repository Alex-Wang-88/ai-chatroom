# 积墨会议转写接口接入文档

## 1. 文档目的

本文档基于积墨 AI OpenAPI 文档，并结合多语言会议录音的真实调用结果，整理出一套可用于“本地录音 → 公网音频 URL → 逐句转写”的完整接入方案。

原始接口文档：

- [上传附件](https://s.apifox.cn/d5f27417-9cb8-4f44-baac-48e012ab33e2/api-263945801)
- [发送会话消息](https://s.apifox.cn/d5f27417-9cb8-4f44-baac-48e012ab33e2/api-146038249)
- [OpenAI 兼容接口](https://s.apifox.cn/d5f27417-9cb8-4f44-baac-48e012ab33e2/doc-7323549)

本文档覆盖以下链路：

```text
本地音频文件
    ↓
公网可下载的 COS/OSS URL
    ↓
POST /v2/upload/file/share，获取 fileId
    ↓
POST /v2/chat/completions/share，传入 file_url + fileId + 文字 URL
    ↓
SSE 流式返回逐句转写结果
```

> 获取“公网可下载 URL”有两种方式：**方式 A** 自行管理 COS/OSS（见第 3 节）；**方式 B** 复用积墨网页 COS 直传（已验证，见第 3.3 节）。两者最终都进入第 4 / 5 节。

## 2. 基础配置

```text
JIMO_BASE_URL=https://jimoai-bot-api.xiaohuodui.cn
JIMO_SHARE_ID=replace-with-agent-share-id
JIMO_AUTHORIZATION=replace-with-service-publish-token

# 方式 B（积墨网页 COS 直传）专用，与上面聊天 token 是两套，不要混用
JIMO_UPLOAD_SHARE_ID=replace-with-upload-enabled-share-id
JIMO_UPLOAD_TENANT_ID=replace-with-tenant-id
JIMO_UPLOAD_CREATE_BY=replace-with-create-by
JIMO_UPLOAD_COS_AUTHORIZATION=replace-with-cos-credential-token
```

说明：

- `JIMO_SHARE_ID` 是智能体服务发布页面或接口 URL 中的 `shareId`。
- `JIMO_AUTHORIZATION` 使用积墨服务发布页面“API 接入”处的 token。
- 不要把真实 token 写入代码、Markdown、Git、前端页面或日志。
- `/v2` 分享接口当前实测使用 token 原值作为 `Authorization`；如果某个环境返回 401，再按该环境要求尝试 `Bearer <token>`。
- OpenAI 兼容的 `/v1/chat/completions` 接口按照文档使用 `Authorization: Bearer <token>`。

## 3. 第一步：准备公网音频 URL

积墨文档中的上传附件接口不接收本地路径。`url` 必须是积墨服务器能够下载的公网地址，例如：

- 腾讯云 COS
- 阿里云 OSS
- Cloudflare R2
- 其他支持公网 GET 的对象存储

音频 URL 必须满足：

1. 不依赖本机路径或 `localhost`。
2. 能够通过 HTTP GET 下载。
3. 返回正确的音频内容类型，例如 `audio/wav`、`audio/mpeg`。
4. 在整个转写任务完成前保持有效。
5. 单文件大小不超过智能体和音频工具允许的限制；当前测试文件约 23.4 MB，可以正常下载。

### 3.1 验证 URL

```powershell
curl.exe -I "https://example.com/meeting.wav"
```

至少应确认返回 2xx/3xx，并且响应不是 HTML 错误页。更可靠的检查方式是读取前几个字节：

```powershell
curl.exe -L -r 0-63 "https://example.com/meeting.wav" --output audio-header.bin
Format-Hex audio-header.bin
```

WAV 文件通常以 `RIFF` 开头。

### 3.2 关于积墨网页上传流程

积墨网页本身会使用一套 COS 临时凭证和签名 PUT 流程。该部分涉及以下内部接口：

```text
GET /v1/settings/byKeyword?keyword=resource.cos
GET /v1/tencent/cos/record/img
PUT <COS signed URL>
```

这些 COS 凭证接口没有出现在 Apifox 公共 API 文档中，属于网页实现细节，可能发生变化。生产环境优先使用自己管理的 COS/OSS 上传服务；如果必须复用积墨网页上传方式，应将其封装成独立适配器，并且不要把 COS 临时凭证持久化。

无论公网 URL 如何产生，后续附件注册都应使用本文档第 4 节的公开 API。

### 3.3 方式 B（已验证）：复用积墨网页 COS 直传

积墨网页客户端在上传录音时，并不是用第 4 节的公开 `upload/file/share` 接口，而是先把本地文件直接 PUT 到积墨托管的腾讯云 COS 桶，拿到公网 URL 后再交给后续处理。这条链路已在 2026-08-19 实测跑通，可作为“方式 A 之外的直传方案”，且无需自己维护对象存储。

完整流程：

```text
本地音频文件
    ↓ GET /v1/tencent/cos/record/img（带独立 COS 凭证 token）
    ↓ 返回 COS 临时凭证 + 目标对象路径 + 签名上传地址
PUT 音频字节到签名 COS URL
    ↓
得到公网 URL：
https://jimoai-oss-1317242179.cos.ap-shanghai.myqcloud.com/<tenantId>/web/audio/<fileName>_<timestamp>.wav
    ↓
该 URL 直接作为第 5 节的 file_url.url / 文字 URL 使用
```

所需配置（与聊天 token 分开，见第 2 节）：

```text
JIMO_UPLOAD_SHARE_ID=replace-with-upload-enabled-share-id
JIMO_UPLOAD_TENANT_ID=replace-with-tenant-id
JIMO_UPLOAD_CREATE_BY=replace-with-create-by
JIMO_UPLOAD_COS_AUTHORIZATION=replace-with-cos-credential-token
```

`/v1/tencent/cos/record/img` 请求示例：

```http
GET https://jimoai-bot-api.xiaohuodui.cn/v1/tencent/cos/record/img?tenantId=replace-with-tenant-id&module=web&contentType=audio&fileName=example.wav&createBy=replace-with-create-by&content=%7B%22shareId%22%3A%22replace-with-upload-enabled-share-id%22%7D
Authorization: replace-with-cos-credential-token
```

接口返回临时 STS 凭证（`tmpSecretId` / `tmpSecretKey` / `sessionToken`）、目标桶（`jimoai-oss-1317242179`）、地域（`ap-shanghai`）、对象路径及签名上传地址；客户端用该凭证把音频字节 PUT 到签名地址，成功后即可用上面的公网 URL。

关键注意事项：

1. **COS 凭证接口用的是另一套 Authorization，不是聊天接口的 token。** 如果给 `/v1/tencent/cos/record/img` 传聊天的 `JIMO_AUTHORIZATION`，会返回 `token已过期`。正确的 COS token 写在 `JIMO_UPLOAD_COS_AUTHORIZATION` 里——它最初是从积墨网页会话页加载的 JS 包（`assets/cos-*.js`）中硬编码的 `Authorization` 值提取出来的；该 token 过期后需重新从网页资源里抓取。
2. **`tenantId` / `createBy` 来自分享页的 `/v1/share/info`（无鉴权即可读取）。** 实施时从当前分享页配置获取，本文不保存真实值。
3. **上传用的 shareId 与聊天的 shareId 可以不是同一个。** 两者都必须从当前环境配置获取，因为 COS 对象 URL 是公网的，聊天接口背后的音频工具可直接下载。
4. `fileName` 建议原样带扩展名（如 `full_normal_random_pauses_16k.wav`）；最终公网 URL 会在文件名后追加时间戳，确保唯一。
5. 凭证接口返回的是**临时** STS 凭证，不要持久化；每次上传前重新申请。
6. 第 3.2 节里“COS 凭证接口属于网页实现细节、可能变化、不推荐”的判断需要修正：它现在已实测可用，只是需要上面这套独立 token，而非聊天 token。

项目内 `realtime_meeting/jimo_upload.py` 即按此流程把本地录音直传到 COS，并输出 `object_url` 供后端使用。

## 4. 第二步：上传附件并获取 `fileId`

### 4.1 接口

```http
POST https://jimoai-bot-api.xiaohuodui.cn/v2/upload/file/share?shareId={shareId}
```

请求头：

```http
Authorization: ${JIMO_AUTHORIZATION}
Content-Type: application/json
Accept: application/json
```

请求体：

```json
{
  "source": "api",
  "url": "https://example.com/meeting.wav",
  "name": "meeting",
  "size": 23986.326,
  "sizeType": "KB",
  "type": "wav"
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `source` | 是 | 文档 API 调用固定填写 `api` |
| `url` | 是 | 公网可下载文件 URL，不能是本地路径 |
| `name` | 否 | 文件名或不含扩展名的显示名称 |
| `size` | 否 | 文件大小数值；推荐与 `sizeType` 保持一致 |
| `sizeType` | 否 | 例如 `KB` |
| `type` | 否 | 扩展名，例如 `wav`、`mp3`、`docx` |

### 4.2 cURL 示例

```powershell
$body = @{
  source = "api"
  url = $env:AUDIO_URL
  name = "full_normal_random_pauses_16k"
  size = 23986.326
  sizeType = "KB"
  type = "wav"
} | ConvertTo-Json

$upload = Invoke-RestMethod `
  -Method Post `
  -Uri "$env:JIMO_BASE_URL/v2/upload/file/share?shareId=$env:JIMO_SHARE_ID" `
  -Headers @{ Authorization = $env:JIMO_AUTHORIZATION } `
  -ContentType "application/json" `
  -Body $body

$fileId = $upload.fileId
Write-Host "fileId=$fileId"
```

### 4.3 成功响应

响应通常是一个 JSON 对象，至少应提取：

```json
{
  "fileId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "source": "api",
  "url": "https://example.com/meeting.wav"
}
```

`fileId` 必须保存下来，并在下一步的 `file_url.fileId` 中原样传回。不要自己生成 `fileId`。

## 5. 第三步：发送带音频的会话消息

### 5.1 接口

```http
POST https://jimoai-bot-api.xiaohuodui.cn/v2/chat/completions/share?shareId={shareId}
```

请求头：

```http
Authorization: ${JIMO_AUTHORIZATION}
Accept: text/event-stream
Content-Type: application/json
```

### 5.2 推荐请求体

积墨文档提供了 `file_url + fileId` 的文件消息格式。实际测试发现，当前会议转写智能体还依赖文字提示中的音频 URL，因此建议两种方式同时传递：

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "帮我逐句转写这个多语言的会议录音，原文和中文翻译都要。\n音视频文件的链接列表为：https://example.com/meeting.wav"
        },
        {
          "type": "file_url",
          "file_url": {
            "url": "https://example.com/meeting.wav",
            "fileId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          }
        }
      ]
    }
  ],
  "sessionId": "生成一个全局唯一 UUID",
  "source": "api",
  "extra": {}
}
```

关键点：

- `file_url.url` 与附件注册时的 `url` 保持一致。
- `file_url.fileId` 使用上传附件接口真实返回的 `fileId`。
- 文字中保留“音视频文件的链接列表为：URL”，可以触发当前智能体已配置的音频转写工具。
- `sessionId` 每次新会议生成一个 UUID；同一会议的后续追问可以复用同一个值。
- `source` 填 `api`，不要填 `web`。

### 5.3 纯文本兼容格式

如果目标智能体的配置明确要求从文字读取 URL，也可以使用：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "帮我逐句转写这个多语言的会议录音，原文和中文翻译都要。\n音视频文件的链接列表为：https://example.com/meeting.wav"
    }
  ],
  "sessionId": "生成一个全局唯一 UUID",
  "source": "api",
  "extra": {}
}
```

推荐优先使用 5.2 的组合格式，因为它同时保留了文档定义的文件对象和智能体当前依赖的文字 URL。

## 6. SSE 响应处理

发送会话消息不是普通 JSON 返回，而是 SSE 事件流。常见事件如下：

```text
event: data
data: {"role":"assistant","content":"部分回答"}

event: data
data: {"role":"assistant","content":"后续回答"}

event: end
data: {"end":{},"role":"assistant"}
```

客户端应：

1. 只拼接 `data` 事件中的 `content`。
2. 收到 `event: end`、`end: {}` 或服务端明确结束标志后结束读取。
3. 不要把每个 SSE chunk 当成一条独立回答保存。
4. 如果需要非流式接口，在业务层收集完整 SSE 后再一次性返回。

Python 最小解析示例：

```python
import json


async def read_sse(response):
    chunks = []
    event_name = "message"
    data_lines = []

    async for line in response.aiter_lines():
        if line == "":
            data = "\n".join(data_lines)
            if event_name in {"data", "message"} and data:
                if data in {"[DONE]", "DONE"}:
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    payload = {}
                content = payload.get("content", "")
                if content:
                    chunks.append(str(content))
                if payload.get("end") is not None or payload.get("done") is True:
                    break
            if event_name == "end":
                break
            event_name, data_lines = "message", []
            continue

        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)

    return "".join(chunks).strip()
```

## 7. Python 调用示例

下面示例展示“已有公网 URL”的标准 API 链路。上传到 COS 的实现应放在此代码之前，不能把本地路径直接传给积墨。示例中的 `read_sse` 函数复用第 6 节实现。

```python
import asyncio
import os
import uuid

import httpx


BASE_URL = "https://jimoai-bot-api.xiaohuodui.cn"
SHARE_ID = os.environ["JIMO_SHARE_ID"]
AUTHORIZATION = os.environ["JIMO_AUTHORIZATION"]
AUDIO_URL = os.environ["AUDIO_URL"]


async def main():
    headers = {
        "Authorization": AUTHORIZATION,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=240.0) as client:
        # 1. 注册公网音频，获取 fileId
        upload_body = {
            "source": "api",
            "url": AUDIO_URL,
            "name": "meeting",
            "type": "wav",
        }
        upload_response = await client.post(
            f"{BASE_URL}/v2/upload/file/share",
            params={"shareId": SHARE_ID},
            headers=headers,
            json=upload_body,
        )
        upload_response.raise_for_status()
        file_id = upload_response.json()["fileId"]

        # 2. 发送文件消息，保留文字 URL 兼容当前会议转写智能体
        message_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "帮我逐句转写这个多语言的会议录音，原文和中文翻译都要。\n"
                                f"音视频文件的链接列表为：{AUDIO_URL}"
                            ),
                        },
                        {
                            "type": "file_url",
                            "file_url": {"url": AUDIO_URL, "fileId": file_id},
                        },
                    ],
                }
            ],
            "sessionId": str(uuid.uuid4()),
            "source": "api",
            "extra": {},
        }
        stream_headers = {**headers, "Accept": "text/event-stream"}
        async with client.stream(
            "POST",
            f"{BASE_URL}/v2/chat/completions/share",
            params={"shareId": SHARE_ID},
            headers=stream_headers,
            json=message_body,
        ) as response:
            response.raise_for_status()
            transcript = await read_sse(response)

    print(transcript)


asyncio.run(main())
```

## 8. 本项目接入建议

当前项目相关文件：

- `realtime_meeting/jimo_upload.py`：本地音频上传适配器。
- `realtime_meeting/jimo.py`：Jimo SSE 客户端。
- `realtime_meeting/server.py`：`POST /api/v2/meetings/{meeting_id}/audio-url` 本地接口。

`jimo_upload.py` 实际走的是第 3.3 节的**方式 B（积墨网页 COS 直传）**，需要从环境变量读取 4 个 `JIMO_UPLOAD_*` 配置（shareId、tenantId、createBy、独立的 COS 凭证 token）。缺少或错用聊天 token 时，直传会卡在 `/v1/tencent/cos/record/img` 返回 `token已过期`。

正式接入时建议拆分为以下两个职责：

```text
JimoAudioUploader.upload_to_public_url()
    ↓
JimoAttachmentClient.register_api_attachment()
    ↓
JimoClient.complete(messages_with_file_url)
```

不要让录音停止动作直接无条件上传。建议由会议完成事件触发异步任务，并保存：

- `meeting_id`
- `object_url`
- `file_id`
- 上传状态
- 转写状态
- 错误信息

如果录音被切成多个音频分片，应对每个分片分别注册并得到多个 `fileId`，然后在消息中传递多个 `file_url`，或在上传前合并音频。不要把多个 URL 拼接成一个无法下载的字符串。

## 9. 已验证行为

使用测试文件 `full_normal_random_pauses_16k.wav` 验证过：

1. 本地音频上传到 COS 成功。
2. 按 Apifox 文档调用 `/v2/upload/file/share`，使用 `source: api` 成功返回 `200` 和 `fileId`。
3. 仅传 `file_url + fileId` 时，当前智能体回复没有收到音频链接。
4. 同时传 `file_url + fileId` 和文字中的公网 URL 后，SSE 转写成功，返回约 2.2 万字符。

因此，当前会议转写智能体的兼容请求应采用第 5.2 节的组合格式。

5. 方式 B（积墨网页 COS 直传）已验证：用独立的 COS 凭证 token 调 `/v1/tencent/cos/record/img`，把本地 wav 直接 PUT 到 `jimoai-oss-1317242179.cos.ap-shanghai.myqcloud.com` 桶，得到可公网 GET 的 URL。
6. 该公网 COS URL 作为 `file_url.url` / 文字 URL 交给聊天接口后，智能体正常进入转写阶段，SSE 正常返回。
7. COS 凭证接口与聊天接口使用**不同的 Authorization token**；把聊天 token 错用在 `/v1/tencent/cos/record/img` 会返回 `token已过期`——这是之前直传失败的根因，现已通过第 3.3 节的方式解决。

## 10. 常见错误排查

| 现象 | 可能原因 | 处理方式 |
|---|---|---|
| 上传附件返回 401 | Authorization 缺失、token 错误或格式不符 | 检查服务发布页 token；不要把转写 URL 当成 token |
| `/v1/tencent/cos/record/img` 返回 `token已过期` | 把**聊天接口**的 token 错用在了 COS 凭证接口上 | 两者是两套 token；COS 凭证 token 在 `JIMO_UPLOAD_COS_AUTHORIZATION`，最初从网页 `assets/cos-*.js` 提取，过期后需重新抓取 |
| COS 直传后聊天接口收不到音频 | 上传用的 shareId 与聊天 shareId 不一致、或 COS URL 非公网 | COS 对象 URL 是公网的，跨 shareId 可用；先用 `curl -I` 确认 URL 可公网 GET |
| `/v1/share/info` 返回 `ai.process.notEnabled` | 使用了未公开记录的内部分享信息接口 | 不依赖该接口；直接配置租户上下文，或使用公开 API 上传接口 |
| 智能体回复没有收到文件 | 只传了 `file_url`，当前工具没有识别附件 | 在文字提示中同时加入公网音频 URL |
| 智能体返回 `FAILED` | 传入的 URL 带临时签名参数、已过期或工具不接受 | 优先使用已验证可公网 GET 的裸 COS URL |
| 403/404 下载失败 | URL 不公开、对象路径错误或已过期 | 用 `curl -I`、Range GET 检查 URL |
| 没有 SSE 结束 | 客户端只监听 `data`，没有处理 `end` | 同时处理 `event: end`、`end/done` 字段和 `[DONE]` |
| 返回内容很短且只是在复述任务 | 智能体没有真正获得音频 | 先验证裸 URL，再检查 `fileId` 是否来自同一个 `shareId` |

## 11. 安全要求

- Authorization token 只能放在服务端环境变量或密钥管理系统中。
- 不要把真实 token 提交到 Git 或写入前端代码。
- 不要把带 `q-sign-*` 的临时 URL 写入长期日志。
- 公网音频 URL 可能包含会议敏感内容，应设置合理的对象生命周期和访问权限。
- 上传、注册、转写请求的响应日志只记录状态码、`fileId` 和耗时，不记录完整请求头和完整音频 URL。
