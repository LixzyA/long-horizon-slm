#!/bin/sh
set -eu
export HOME=/tmp/pi-home
export PI_CODING_AGENT_DIR="$HOME/.pi/agent"
mkdir -p "$PI_CODING_AGENT_DIR" /workspace/.pi-sessions
node - <<'JS'
const fs = require("fs");
const path = require("path");
const kind = process.env.BACKEND_KIND || "llamacpp";
const hosted = kind !== "llamacpp";
const provider = hosted ? kind : "llamacpp";
const model = kind === "openrouter" ? "deepseek/deepseek-v4.1-flash-1017" : kind === "huggingface" ? "deepseek-ai/DeepSeek-V4.1-Flash" : "Qwen3.5-custom-32k";
const config = {providers: {[provider]: {
  api: "openai-completions",
  baseUrl: "http://gateway:8080/v1",
  apiKey: "$MODEL_PROXY_TOKEN",
  models: [{id: model, reasoning: true, contextWindow: hosted ? 1048576 : 32768, maxTokens: 16384, compat: {supportsStore: false, supportsDeveloperRole: false, maxTokensField: "max_tokens"}}]
}}};
fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR, "models.json"), JSON.stringify(config));
JS
if [ "${BACKEND_KIND:-llamacpp}" = huggingface ]; then
  exec pi --provider huggingface --model deepseek-ai/DeepSeek-V4.1-Flash --thinking "$THINKING_MODE" --mode rpc --session-dir /workspace/.pi-sessions
fi
if [ "${BACKEND_KIND:-llamacpp}" = openrouter ]; then
  exec pi --provider openrouter --model deepseek/deepseek-v4.1-flash-1017 --thinking "$THINKING_MODE" --mode rpc --session-dir /workspace/.pi-sessions
fi
exec pi --provider llamacpp --model Qwen3.5-custom-32k --thinking "$THINKING_MODE" --mode rpc --session-dir /workspace/.pi-sessions
