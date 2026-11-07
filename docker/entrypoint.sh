#!/bin/sh
set -eu
export HOME=/tmp/pi-home
export PI_CODING_AGENT_DIR="$HOME/.pi/agent"
mkdir -p "$PI_CODING_AGENT_DIR" /workspace/.pi-sessions
node - <<'JS'
const fs = require("fs");
const path = require("path");
const config = {providers: {llamacpp: {
  api: "openai-completions",
  baseUrl: "http://gateway:8080/v1",
  apiKey: "$MODEL_PROXY_TOKEN",
  models: [{id: "Qwen3.5-custom-32k", reasoning: true, contextWindow: 32768, maxTokens: 16384, compat: {supportsStore: false, supportsDeveloperRole: false, maxTokensField: "max_tokens"}}]
}}};
fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR, "models.json"), JSON.stringify(config));
JS
exec pi --provider llamacpp --model Qwen3.5-custom-32k --thinking "$THINKING_MODE" --mode rpc --session-dir /workspace/.pi-sessions
