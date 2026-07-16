#!/usr/bin/env sh
# Entry point for the okx-a2a daemon on an always-on host (e.g. Railway).
# Keeps the daemon in the FOREGROUND so the container's main process stays alive.
set -e

: "${OKX_AGENT_TASK_HOME:=/data/.okx-agent-task}"
: "${OKX_A2A_AI_PROVIDER:=claude}"
export OKX_AGENT_TASK_HOME OKX_A2A_AI_PROVIDER

mkdir -p "$OKX_AGENT_TASK_HOME"

echo "[start] OKX_AGENT_TASK_HOME=$OKX_AGENT_TASK_HOME  provider=$OKX_A2A_AI_PROVIDER"

# 1) Environment self-check. This is exactly `okx-a2a doctor --fix` — but here it
#    is meaningful because the host IS 24/7 and state is on a persistent volume.
#    It validates Node, the AI runtime binding, and login. If login is missing it
#    will say so (see README: provision the volume with an authenticated home).
okx-a2a doctor --fix || echo "[start] doctor reported issues (see logs); continuing to daemon start"

# 2) Run the daemon in the foreground. `daemon start` normally backgrounds and
#    installs OS autostart; in a container we want it attached to PID 1. If your
#    installed version supports --foreground it is used; otherwise we start it and
#    tail its log so the container does not exit.
if okx-a2a daemon start --ai-provider "$OKX_A2A_AI_PROVIDER" --foreground 2>/dev/null; then
  :
else
  echo "[start] --foreground unsupported on this version; starting detached + tailing"
  okx-a2a daemon start --ai-provider "$OKX_A2A_AI_PROVIDER"
  LOG="$OKX_AGENT_TASK_HOME/daemon.log"
  # Keep PID 1 alive and stream the daemon log to Railway logs.
  touch "$LOG"
  exec tail -n +1 -f "$LOG"
fi
