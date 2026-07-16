# okx-a2a message-layer daemon (24/7) for OKX.AI.
# Runs the XMTP agent-to-agent daemon that delivers other agents' messages +
# system notifications to a co-located AI CLI, which processes the task.
#
# NOTE: okx-a2a is designed for an always-on host. Railway CAN keep this process
# alive 24/7 with a persistent volume, but see README for the two real caveats:
# (1) it needs an AI CLI runtime + that provider's API key, and
# (2) the first login is interactive — provision it into the volume (README).
FROM node:22-slim

# Node >= 22.13 is required by @okxweb3/a2a-node (this base is 22.x).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

# The A2A daemon itself...
RUN npm i -g @okxweb3/a2a-node

# ...and an AI CLI it can drive. Default: Claude Code CLI. Swap for codex/hermes/
# openclaw as desired and set OKX_A2A_AI_PROVIDER to match.
RUN npm i -g @anthropic-ai/claude-code || true

# State/identity home lives on the mounted volume so XMTP keys + login survive
# redeploys and container recycling.
ENV OKX_AGENT_TASK_HOME=/data/.okx-agent-task
ENV OKX_A2A_AI_PROVIDER=claude
ENV XMTP_ENV=production

WORKDIR /app
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
