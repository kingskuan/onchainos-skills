# Agentic Volume Booster — Summary

## Overview

`agentic-volume-booster` is a single-purpose Skill that helps Agentic Wallet trading-competition participants **meet a qualifying-volume threshold (default $1,000)** with the **lowest possible capital friction (default ≤ 0.5% of wallet)**.

It does this by:

1. Reading the user's wallet status, competition registration, and current cumulative volume.
2. Auto-picking the deepest-liquidity, non-excluded token route on the target chain (e.g. JUP on Solana).
3. Planning a sequence of round-trips (buy → immediate sell) sized to hit the volume target while staying under the friction budget.
4. Showing the plan to the user for one explicit confirmation.
5. Executing the schedule autonomously, **stopping immediately** if any of: friction exceeds budget, price impact spikes 5×, wallet falls below the $100 participation-prize floor, or a leg fails simulation.

The skill is **not a profit strategy**. It produces zero or slightly negative PnL by design — round-trips have to pay LP fees and gas. The win is qualifying the user for the leaderboard / participation prize at minimum cost.

## Validation

Real-world test on Solana, May 2026:

| Metric | Value |
|---|---|
| Starting capital | $414.42 |
| Target volume | $1,000 |
| Friction budget | $2.07 (0.5% of capital) |
| Realized volume | **$1,038** (104% of target) |
| Realized friction | **$0.43** (0.10% of capital) |
| Round-trips executed | 4 |
| Tx count | 8 |
| Token used | JUP (Solana) |
| Routes | USDC ↔ JUP × 2, SOL ↔ JUP × 1, plus calibration $30 USDC ↔ JUP |

**Friction came in 5× under budget.** Empirical per-volume friction: 0.04%.

## Prerequisites

1. **`onchainos` CLI** installed and on `PATH`:
   ```sh
   curl -sSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh
   ```
2. **Agentic Wallet logged in**:
   ```sh
   onchainos wallet login <email> --locale <zh-CN|en-US|ja-JP>
   onchainos wallet verify <otp_code>
   ```
3. **Registered for an Agentic Wallet competition**:
   ```sh
   onchainos competition list --status 0
   onchainos competition join --activity-id <id> --evm-wallet <addr> --sol-wallet <addr> --chain-index <id>
   ```
4. **Wallet funded** with at least $200 on the target chain (recommended). The skill will auto-pick a chain where you have liquid balance.

## Quick Start

```text
User: "Help me hit the trading volume requirement, friction under 0.5%."

Agent (via this skill):
  1. Reads wallet & competition status, current volume = 0.
  2. Picks JUP on Solana (deepest non-excluded route, 0.05% LP fee).
  3. Computes plan:
       - 3 round-trips (USDC × 2, SOL × 1)
       - Expected total volume $1,000, friction $0.40
  4. Shows plan, awaits confirmation.
  5. Executes 6 swaps in sequence with live friction tracking.
  6. Reports: realized volume $1,038, friction $0.43 (0.10% of capital).
```

## Parameters

| Param | Default | Description |
|---|---|---|
| `target_volume_usd` | `1000` | Competition leaderboard threshold |
| `friction_budget_pct` | `0.5` | Hard cap as % of session-start capital |
| `chain` | `solana` | Must match a competition-supported chain |
| `route_token` | auto-pick | Override auto-selection of round-trip token |
| `max_rounds` | `6` | Hard cap on number of round-trips |
| `slippage_tolerance` | `0.5` | Per-swap slippage in % |
| `dry_run` | `true` | Default safe — quote only, no execution |

## Safety Highlights

- **Friction budget cap** acts as stop-loss. Auto-halts on overrun.
- **$100 wallet floor** preserves the participation-prize qualification.
- **Per-leg quote re-validation** detects pool degradation mid-execution.
- **Always re-reads on-chain balance** before sell legs (handles Solana SPL dust).
- **Never routes excluded pairs** (USDC↔SOL etc. — they wouldn't count for the competition).
- **TEE signing** — private keys never leave the secure enclave.

## When NOT to Use

This skill is intentionally narrow. Route elsewhere if:

- You want to actually make money on a swap → `okx-dex-swap`.
- You want signal-driven entries → `okx-dex-signal`.
- You want a momentum scan → `okx-dex-token` (hot-tokens).
- You want yield / staking → `okx-defi-invest`.

## Files

```
agentic-volume-booster/
├── .claude-plugin/plugin.json
├── plugin.yaml
├── SKILL.md                     # AI agent entry point — full command docs
├── SUMMARY.md                   # This file
├── LICENSE                      # MIT
└── references/
    ├── friction-model.md        # Friction decomposition + empirical baselines
    ├── token-selection.md       # Deepest-pool scoring algorithm
    └── excluded-pairs.md        # Per-chain stable/native/wrapped matrix
```

## License

MIT
