# v0 停摆项目复活评估（2026-10-25，只读检查）

两个仓库各只有一个 commit（"Initial public release"），均为 2026-09-22 发布快照，之后未动过。

---

## 项目 1：ai-chatroom（FastAPI + React + SQLite 多 AI 群聊）

### 1. LLM 后端接线方式
- **配置**：`backend/app/config.py:15-33` — `jimo_base_url`（默认 `https://jimoai-bot-api.xiaohuodui.cn`）、`jimo_authorization`、`jimo_auth_scheme`（bearer/raw）、每 Agent 的 `jimo_share_url_*`（可选 `/v2/chat/completions/share` 覆盖端点）。
- **客户端**：`backend/app/providers/jimo.py:137-194` `JimoProvider.stream_chat` — httpx 流式 POST，手写 SSE 解析器 `parse_sse_lines`（61-107 行，支持 `event:end`、`[DONE]`、OpenAI 兼容 `choices[].delta`）。159-162 行：检测到端点含 `/v2/chat/completions/share` 时自动附加 `sessionId`、`source=api`、空 `extra`，即已按 积墨 v2 share 协议适配。auth 支持 raw token 原值 / Bearer（115-122），错误信息里对 token 做脱敏（130-135、174）。
- **SSE 断线重连：没有**。`stream_chat` 是单次尝试，`httpx.TimeoutException/HTTPError` 直接抛 `ProviderError`（jimo.py:188-191）；orchestrator 把该条发言标记失败（`service.py:440-441、497-498`）。Free 模式有连续错误计数，`consecutive_errors >= free_error_threshold(默认3)` 时整轮终止（`service.py:839-846`）。仅支持手动单条重试接口 `retry_message`（service.py:1176）。**结论：上游 SSE 一断，当条消息死，无自动重连。**
- 注意区分：项目**自身**的实时层（前后端 WebSocket）反而很健壮 — `frontend/src/pages/ChatRoomPage.tsx:53-113` 指数退避+抖动重连、`after_sequence` 断点续传、epoch 变化检测全量重同步；`backend/app/realtime/event_hub.py:32-55` 环形缓冲回放 + gap 检测发 `sync.required`。

### 2. 今天复活，最先坏什么
1. **本地 `.env` 已过期（最先坏）**：现有 `.env` 只有 21 个键，**完全缺失 `JIMO_SHARE_URL_*`（3个）和 `JIMO_MODEL_*`（3个）** —— 是 share 接线改造之前的旧文件。`config.py:69-76` 查不到 share URL 返回空串 → 走默认 `/v1/chat/completions` + 空 model → 首次请求即失败。
2. **凭证风险**：`.env` 里留有一个 59 字符的 raw `JIMO_AUTHORIZATION`（2026-09 初的凭证）；README:38 明确警告 积墨api.md 历史上含疑似真实凭证，**部署前必须轮换**。积墨api.md:48 也注明 v2 share 实测用 token 原值做 Authorization，401 时再试 Bearer。
3. **API 漂移高风险**：share 接口是抓包逆向的非正式协议（自定义 `type=data/thinking`、`event:end`），`docs/jimo-capability-matrix.md` 最后实测 2026-09-01，且注明"无 usage/model ID 被确认"、取消是否停止上游计费未知。协议/凭证任一变动即坏。
4. **依赖腐化：后端低、前端中**。后端 pyproject 全是宽区间（fastapi>=0.115,<1 等）+ `uv.lock`，风险低（Python 3.12+）。但 `frontend/package.json` **所有依赖都写 `"latest"`**（react/vite/zustand/typescript），只有靠 package-lock.json 锁定 —— 复活时务必 `npm ci` 而非 `npm install`，否则直接拉到最新版可能编译不过。
5. DB：alembic 仅一个迁移 `backend/migrations/versions/0001_initial.py`；`data/` 里还有 check.db、migration_verify*.db 等 7 个测试残留库，应清理。

### 3. 复活清单（按序）
1. **[S]** 轮换积墨凭证：从分享页取新 token + 3 个 share URL，重写 `.env`（补上 6 个缺失键）。
2. **[S]** `python scripts/probe_jimo.py --agent <handle>` 验证 v2 share 协议是否仍按 2026-09-01 的 wire format 工作（重点：`event:end`、`type=thinking` 过滤）。
3. **[S]** 后端：`uv sync`（或 pip install -e .）+ `alembic upgrade head` 在 db 副本上验证；跑 `pytest`。
4. **[S]** 前端：`npm ci`（严禁 npm install，因全是 "latest"），跑 `npm test`。
5. **[M]** 给 `JimoProvider.stream_chat` 加自动重试/重连（如 1-2 次退避重试 + 只在无输出时重发），并把 Free 模式 error_threshold 从"终止"改为"跳过该 Agent 继续"。
6. **[M]**（可选）在 OpenAI 兼容 provider 上加一条通用路径，降低对 积墨 share API 的单点依赖。

### 4. 结论
**rework 后复活**：代码质量与自身实时层都不错，但复活完全卡在外部凭证 + 非正式 share API 的有效性上，且上游 SSE 无重连，需要半天到一天的针对性补强。

### 5. 发布时已知未完成项（README/docs 自述）
- README:7 — model ID 与 wire format 必须 Probe 后再配，"未在代码中臆造"（即发布时 model ID 未确认）。
- capability matrix — 取消是否停止上游计费未知；GLM probe 中途手动取消。
- V0.1 仅纯文本（无图片/语音）；辩论模式设计上不自动继续、无轮数上限（README:11）。

---

## 项目 2：trpg_webui / 夜桌（Next.js16 + React19 + node:sqlite 文字跑团）

### 1. LLM 后端接线方式
- **文本模型**：`server/ai.mjs:53-73` `requestJson` — **非流式** fetch POST `{baseUrl}/chat/completions`（OpenAI 兼容，用户在房间设置里自行填 baseUrl/model/apiKey），Bearer 鉴权，`response_format: {type:"json_object"}`，期望模型返回严格 JSON（`{"publicText":...,"toolCalls":[...]}`），`extractJson`（8-16 行）做围栏剥离后 JSON.parse，失败即抛错。**没有 SSE，无断线重连问题**——由 SQLite 任务队列兜底。
- **队列与重试：有，且是亮点**。`server/jobs.mjs:77-102` `startJobRunner` 每 400ms 轮询 `claimNextJob`；失败走 `store.failJob`（store.mjs:516-517）— **attempts<3 自动重新入队，指数退避（2^n，上限60s），>=3 次才判 failed**，并通过 `job.failed` 事件通知前端"正在自动重试"（page.tsx:560）。图片生成 `processImageJob`（jobs.mjs:32-66）POST `/images/generations`，支持 b64_json 和 URL 下载两种回包。
- **密钥**：房间 AI Key 用 AES-256-GCM 加密落库（store.mjs:19-31），密钥来自 `APP_MASTER_KEY`；注意 store.mjs:16-18 有**硬编码开发默认密钥**，未设 env 时静默使用。
- **房间 SSE**：服务端 `server/index.mjs:106-115` — `text/event-stream`，连接即发 `ready`（含 currentSeq），20s 心跳；**不读 Last-Event-ID、不回放缺口**。前端 `app/page.tsx:437-585` — `EventSource` 靠浏览器原生自动重连，onerror 只置 offline，**没有监听 `ready` 事件、重连后不重新 bootstrap(afterSeq) 补漏** → 断线期间的房间事件在刷新页面前永久丢失。README:12 宣称的"断线后的事件恢复"实际只在页面加载时的 `bootstrap?afterSeq`（index.mjs:101-104）生效。

### 2. 今天复活，最先坏什么
1. **LLM 侧几乎不会坏**：标准 OpenAI 兼容端点 + 密钥在房间运行时配置（非启动期 env），换任何兼容供应商即可。唯一脆点：强依赖 `response_format: json_object` + 严格 JSON 解析，遇到不支持该参数或爱加 Markdown 的模型会整轮失败（但有 3 次队列重试兜底）。
2. **依赖腐化：中**。package.json 全部精确锁版（next 16.2.6、react 19.2.6、vite 8.0.13、vinext 0.0.50）且有 lock 文件，`npm ci` 可复现。真正的风险是**底座是 "site-creator-vinext-starter" 模板**：vinext 0.0.x（0.x 版元框架）+ `@vitejs/plugin-rsc` 0.5.x 属高变动早期生态，模板不升级则永远冻结在 2026-08。
3. **运行时门槛**：`server/store.mjs:5` 用 `node:sqlite`（DatabaseSync），engines 要求 **Node >=22.13**；Dockerfile 用 node:22-bookworm-slim。升级到 Node 24 LTS 需回归测试。
4. **部署必填 env 只有 `APP_MASTER_KEY`**（docker-compose 已用 `${APP_MASTER_KEY:?}` 强制）；不设则用默认开发密钥加密所有房间 Key，属安全隐患。
5. **死代码干扰**：`db/schema.ts` 是空模板（"Intentionally empty"）、`db/index.ts`、`drizzle/`、`drizzle.config.ts`、`worker/index.ts`（Cloudflare 图片优化 worker）全是 vinext 模板残留，真实持久化全在 store.mjs 裸写 SQL（94-165 行 `CREATE TABLE IF NOT EXISTS`，无迁移系统，改表需手写 ALTER）。

### 3. 复活清单（按序）
1. **[S]** `npm ci && npm run server:dev` + 另端 `npm run dev`，确认 Node 22.13+ 环境下 node:sqlite 正常；`npm run test:server`。
2. **[S]** 设置强随机 `APP_MASTER_KEY`，并删掉 store.mjs:16-18 的默认密钥回退（或至少打警告日志）。
3. **[S]** 房间设置里配一个现役 OpenAI 兼容端点（文本 + 图片可不同 baseUrl），跑通 AI KP 一轮 + 一张场景图，验证 json_object 兼容性。
4. **[M]** 修 SSE 断线补洞：前端 `source.addEventListener("ready", ...)` 里用记录的 lastSeq 重新 `bootstrap?afterSeq=<seq>` 回放缺口（服务端 ready 已带 currentSeq，index.mjs:108，改动集中在一处）。
5. **[M]** 清理模板残留（db/、drizzle*、worker/、chatgpt-auth.ts、.openai/.vinext/.wrangler 目录），并给 store.mjs 加个极简 schema_version 表以防未来改表。
6. **[L]**（可选）评估从 vinext 0.0.50 迁到上游新版或纯 Vite/Next 官方栈——不做也能跑，做了才长期可维护。

### 4. 结论
**基本可直接复活**：无外部 API 锁定、任务队列自带重试、依赖全锁版，一个下午加一个周末补 SSE 回放即可用；长期隐患仅在 vinext 0.x 底座。

### 5. 发布时已知未完成项（README/docs 自述）
- README:76 — D&D 模块"后续应只分发有明确再分发许可的 SRD 内容"（版权边界未完全落地）。
- 语音转文字依赖浏览器 SpeechRecognition（page.tsx:9-21 自定义类型垫片），仅 Chromium 系可用、固定 zh-CN。
- 图片模型硬编码 `size: "1024x1024"` + `response_format: b64_json`（jobs.mjs:44），对不支持该参数的供应商无降级。

---

## 共同结论：先复活哪个

**只有一个周末 → 选 夜桌（trpg_webui）**。理由：它的 LLM 接线是标准 OpenAI 兼容 + 队列自动重试，不押注任何非正式 API，依赖全锁版，复活路径就是"npm ci + 配 key + 跑测试 + 修一个 SSE 回放缺口"，成功概率高且成果可长期使用。ai-chatroom 的复活**外部依赖占主导**（积墨凭证必须轮换、share URL 缺失、v2 非正式协议需重新 Probe 验证、上游 SSE 无重连），即使代码本身质量更好，周末大概率耗在外部凭证与协议确认上——建议等积墨侧凭证/协议稳定后，按其清单 1-5 顺序作为第二个周末项目处理；若 3 个月内拿不到新凭证，则归档。
