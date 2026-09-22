# AI Chat Room

桌面优先的多 AI 群聊应用。V0.1 只支持纯文字，所有模型请求均由 FastAPI 后端发起。

## 当前状态

项目已经包含可运行的 FastAPI/React 基础切片、Topic 并行模式、Free 串行模式、SQLite 持久化、SSE Provider 适配、WebSocket 事件和测试骨架。Free 模式默认围绕用户原话题进行最多两轮、每轮每个未禁言 Agent 最多发言一次，并在结束时显示停止原因和真实轮次统计。积墨纯文本接口的 model ID 与具体 wire format 必须使用新凭证运行 `scripts/probe_jimo.py` 后再配置；不要使用 `积墨api.md` 历史内容中的旧凭证。

## AI 辩论

访问前端的“AI 辩论”页面即可单独创建一场辩论。用户可以按主题开始（正方支持、反方反对），也可以手动填写正方和反方立场；两方模型可分别选择，也允许使用同一个模型。正方先开篇，之后点击“让下一方发言”逐次交替调用模型，内容会流式显示。辩论不会自动继续，也不设置总轮数上限。

辩论记录使用独立的 `/api/v1/debates` 接口保存，包含辩题、双方立场、模型配置和逐轮发言；前端可重新加载记录并修改名称。发言通过 `/api/v1/debates/respond/stream` 流式生成，不写入普通聊天室会话；普通聊天室的全局提示词和消息流不受影响。

## 开发启动

1. 复制 `.env.example` 为 `.env`，填入服务端积墨凭证、每个 Agent 的 share URL 和 Probe 确认的 model ID。`.env` 仅用于本地或部署环境，并已被 `.gitignore` 忽略；不要将真实凭证写入仓库。
2. Python 3.12+：`python -m venv .venv`，然后安装 `pip install -e .[dev]`。
3. 前端：进入 `frontend` 执行 `npm install`。
4. 启动后端：`uvicorn app.main:app --reload --app-dir backend`。
5. 启动前端：`npm run dev --prefix frontend`。

也可以在准备好本地 `.env` 后使用 `docker compose up` 启动开发容器；服务仍只绑定 localhost。

## Probe

`python scripts/probe_jimo.py --model <confirmed-model-id>` 只输出脱敏结果；完整 token 不得写入日志或提交 Git。Probe 结果应整理到 `docs/jimo-capability-matrix.md`。

当前接入的 `/v2/chat/completions/share` URL 通过 `JIMO_SHARE_URL_DEEPSEEKV4LASH`、`JIMO_SHARE_URL_QWEN36FLASH`、`JIMO_SHARE_URL_GLM53FLASH` 配置；该流程使用 `JIMO_AUTH_SCHEME=raw`、`sessionId` 和 `source=api`。真实 model ID 仍以 Probe 结果为准，未在代码中臆造。

## 测试

后端：`pytest`。前端：`npm test --prefix frontend`。端到端测试需要先启动后端和前端。
凭证扫描：`python scripts/secret_scan.py`（本地 `.env` 永不纳入扫描或 Git）。

## 安全

当前仓库不保存任何真实 token。由于原始 API 文档曾包含疑似真实凭证，相关凭证必须在部署前轮换。
