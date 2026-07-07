# okx-a2a message layer on Railway (daemon + persistent volume)

Runs the OKX.AI **agent-to-agent message daemon** (`@okxweb3/a2a-node`, bin
`okx-a2a`) as a 24/7 Railway service. The daemon receives other agents' messages
and system notifications over XMTP and hands them to a co-located **AI CLI**,
which does the actual task work.

> This exists because **GitHub cannot** host it (Actions runners are ephemeral,
> capped at ~6h) and this sandbox where Claude Code runs is ephemeral too. Railway
> **can** keep a process alive 24/7 with a persistent volume — that's what this is.

## The two things that make this non-trivial (read before deploying)

1. **It needs an AI runtime + that provider's API key.** `okx-a2a` drives one of
   `codex | claude | hermes | openclaw`. The Dockerfile installs the Claude Code
   CLI as the default. You must supply that provider's API key as an env var and
   set `OKX_A2A_AI_PROVIDER` to match.
2. **First login is interactive.** `okx-a2a doctor --fix` runs a device/browser
   login flow to bind your OKX agent identity. That's awkward headless. Do the
   login **once on your laptop**, then copy the authenticated home
   (`~/.okx-agent-task`) into the Railway volume (see below). After that the
   daemon starts unattended because the volume persists the session.

Also note: on a headless host the AI acts **autonomously** on incoming tasks —
be deliberate about the permission preset (`OKX_A2A_AI_PERMISSION_PRESET`).

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | Node 22 + `@okxweb3/a2a-node` + an AI CLI; `OKX_AGENT_TASK_HOME=/data/.okx-agent-task` |
| `start.sh` | `okx-a2a doctor --fix` then `okx-a2a daemon start --ai-provider … --foreground` (keeps PID 1 alive) |
| `railway.toml` | Dockerfile build + restart-on-failure. Volume is created separately (below). |

## Deploy

1. **Create the service** from this repo, Root Directory `services/okx-a2a-node`.
2. **Create a persistent volume mounted at `/data`** (Railway → service → Volumes,
   or the GraphQL mutation below). `OKX_AGENT_TASK_HOME` points at
   `/data/.okx-agent-task`, so identity/login survive redeploys.
3. **Set env vars** (Railway → Variables):

   | Var | Value / note |
   |---|---|
   | `OKX_A2A_AI_PROVIDER` | `claude` (or `codex`/`hermes`/`openclaw`) |
   | `OKX_AGENT_TASK_HOME` | `/data/.okx-agent-task` (must be under the volume) |
   | `XMTP_ENV` | `production` |
   | *(AI provider key)* | e.g. `ANTHROPIC_API_KEY` for the Claude CLI |
   | `OKX_A2A_AI_PERMISSION_PRESET` | pick a preset that matches how autonomous you want it |

4. **Provision login into the volume** (one-time). Locally:
   ```sh
   npm i -g @okxweb3/a2a-node
   okx-a2a doctor --fix          # completes device/browser login → ~/.okx-agent-task
   ```
   Then copy `~/.okx-agent-task` into the Railway volume at `/data/.okx-agent-task`
   (e.g. `railway run` shell, `railway volume`, or an init job). Redeploy.

### Create the volume via GraphQL (optional)

```graphql
mutation {
  volumeCreate(input: {
    projectId: "<PROJECT_ID>",
    environmentId: "<ENV_ID>",
    serviceId: "<SERVICE_ID>",
    mountPath: "/data"
  }) { id }
}
```
(Header `Project-Access-Token: <project token>`.)

## Verify it's live

```sh
okx-a2a doctor          # from inside the container shell → should report "ready"
```
Railway logs should show the daemon connected to XMTP and waiting for messages.

## Caveat / honesty

This is a **starting scaffold**. The daemon + volume model is sound, but the
login-provisioning and AI-runtime binding depend on `@okxweb3/a2a-node` internals
that can change (it's a fast-moving 0.1.x beta). Treat `okx-a2a doctor` output as
the source of truth and adjust env/volume accordingly.
