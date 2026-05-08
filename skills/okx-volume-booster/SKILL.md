---
name: okx-volume-booster
description: "Complete trading-volume thresholds for OKX Agentic Wallet competitions with minimum capital friction. Detects current cumulative volume, picks the deepest-liquidity non-excluded token route on the target chain, plans a round-trip schedule that stays inside a hard friction budget (default 0.5% of capital), and executes step-by-step with live friction tracking and auto-stop on overrun. Triggers: 'complete competition volume', 'help me hit the $1000 trading volume', 'low-friction volume booster', 'trade volume completer', '刷交易量', '凑比赛交易量', '完成累计交易量门槛'. Do NOT use for: profit-seeking momentum trading (use okx-dex-swap), signal-driven entries (okx-dex-signal), or generic swaps. This skill assumes the user is registered for an Agentic Wallet competition and wants to qualify for the leaderboard or participation prize with the lowest possible cost."
license: MIT
metadata:
  author: kingskuan
  version: "0.1.0"
  homepage: "https://github.com/okx/onchainos-skills"
---

# OKX Volume Booster

Efficiently meet trading-competition volume thresholds (default $1,000) with hard-capped capital friction (default 0.5%). Built on the `onchainos` CLI; no novel infra.

## Step 0 — Re-route check (run before every other step)

This skill is **scoped narrowly**. Re-route the user before doing anything else if the intent is not pure volume completion.

| User intent | Route to |
|---|---|
| "Buy / sell / swap a specific token" (profit-seeking) | `okx-dex-swap` |
| "What's smart money buying?" / signal-driven entries | `okx-dex-signal` |
| "Find a momentum token to long" | `okx-dex-token` (hot-tokens) |
| "Stake / lend / yield-farm" | `okx-defi-invest` |
| "Pure stablecoin → token round-trips to clear a competition volume gate" | **Stay** |
| "刷交易量 / 凑量 / 完成累计交易量门槛" | **Stay** |

If the user mixes intents (e.g. "刷交易量 but I also want to long XYZ"), split: stay here for the volume part, dispatch `okx-dex-swap` for the directional part.

## What this skill produces

A round-trip plan that:
1. **Hits target volume** (default $1,000 — competition leaderboard threshold) ± 10%
2. **Stays under hard friction budget** (default 0.5% of total capital)
3. **Respects competition exclusion rules** — never routes through pairs that don't count toward qualifying volume
4. **Reports live friction** after every leg; auto-stops if budget would be breached

## Pre-flight Checks

<MUST>
1. Wallet must be logged in. Run `onchainos wallet status`. If `loggedIn: false`, defer to `okx-agentic-wallet` Authentication flow.
2. Competition registration confirmed. Run `onchainos competition user-status` (omit `--activity-id` to scan all). If no entry has `joinStatus=1`, ask the user which competition to join and dispatch `okx-growth-competition` Step 3.
3. Target chain must be one of the **competition-supported chains**. Read the chain from the user's joined competition's `chainName` (plus the always-on Solana hardcoding — see `okx-growth-competition/SKILL.md` "Facts about every Agentic Wallet competition"). Trades on any other chain do NOT count toward competition volume.
</MUST>

## Parameter Rules

| Param | Default | Description |
|---|---|---|
| `target_volume_usd` | `1000` | Competition leaderboard threshold. Lower if only chasing the participation prize ($100). |
| `friction_budget_pct` | `0.5` | Hard cap, expressed as % of **total wallet capital** at session start. NOT % of volume. |
| `chain` | `solana` | One of the competition-supported chains. Always check `competition_detail` first. |
| `route_token` | auto-pick | Override the token used for round-trips. Leave empty to auto-pick the deepest-liquidity non-excluded token. |
| `max_rounds` | `6` | Safety cap — never run more than this many round-trips even if budget allows. |
| `slippage_tolerance` | `0.5` | Per-swap slippage in %. Applied to both legs. |
| `dry_run` | `true` | If true, only quote and report; do NOT execute. Set to `false` to actually swap. |

## Friction Model

> Detail: `references/friction-model.md`

Per round-trip friction (one buy + one immediate sell):

```
friction_round_trip ≈ 2 * (LP_fee + price_impact + slippage_realized) + 2 * tx_gas_usd
```

For deep-liquidity tokens (e.g. Solana JUP, USDC pair):
- Empirical one-way: ~0.07% (LP fee + impact)
- Round-trip: ~0.14–0.20%
- Solana priority gas: ~$0.01 per tx, negligible at $1k+ trade size

Capital-percent friction = total_friction_usd / wallet_capital_usd.

## Token Selection Algorithm

> Detail: `references/token-selection.md`

```
1. Read competition exclusion rules (stable ↔ stable, native ↔ stable, native ↔ wrapped-native — see references/excluded-pairs.md)
2. Filter `onchainos token hot-tokens --chain <chain> --liquidity-min 200000 --volume-min 500000` by:
   - tokenSymbol NOT IN {stables, natives, wrapped_natives}
   - riskControlLevel == 1
   - top10HoldPercent < 50
3. For each candidate, fetch `onchainos token liquidity --address <ca>` and pick the pool with max(liquidity_usd) AND lowest LP_fee_pct
4. Score = liquidity_usd / (LP_fee_pct + 0.001)  -- avoid division-by-zero on free pools
5. Pick the highest score. Report rationale.
```

For Solana competitions, **JUP is the empirical winner** at the time of writing (Apr–May 2026): $4M+ aggregate USDC-routed liquidity, 0.05% LP fee on the best pool, no excluded-pair constraint.

## Command Index

| # | Command | Description | Auth |
|---|---|---|---|
| V1 | `progress` | Read wallet status + competition status; compute current volume vs target | Wallet |
| V2 | `plan --target-volume <usd> --friction-budget-pct <pct> [--chain <c>] [--route-token <addr>]` | Quote-only: produce a round-trip schedule with live friction estimate | Wallet |
| V3 | `execute --plan-id <id>` | Run the schedule produced by `plan`. Stops on friction overrun. | Wallet |
| V4 | `report` | Final summary: volume hit, friction realized, txs, P&L | Wallet |

These are conceptual operations. Implementation calls into `onchainos swap quote/execute`, `onchainos wallet balance`, and `onchainos competition user-status`.

## Execution Flow

### V1 — Progress

```bash
onchainos wallet balance --force
onchainos competition user-status --evm-wallet <evm> --sol-wallet <sol>
```

Output: current cumulative volume (NOT directly returned by API — must be inferred by the agent from join status + recent trade history; see "Volume estimation" below).

### V2 — Plan

```
1. Capital = wallet.totalValueUsd  (excluding non-tradable / staking positions)
2. friction_budget_usd = capital * (friction_budget_pct / 100)
3. token = pick_token(chain) using Token Selection Algorithm
4. expected_friction_per_dollar_volume = empirical_estimate(token)  -- start from 0.0002 (0.02%) for deep pools
5. max_total_volume_within_budget = friction_budget_usd / expected_friction_per_dollar_volume
6. plan_volume = min(target_volume_usd, max_total_volume_within_budget * 1.5)  -- 50% headroom check
7. round_size = plan_volume / max_rounds / 2  -- per-direction
8. round_size = min(round_size, capital * 0.8)  -- never put 100% of capital in one trade
9. Generate schedule: alternate USDC↔token and SOL↔token rounds; recycle output to chain inputs
10. For each scheduled leg, run `onchainos swap quote` (read-only) and verify expected_friction_per_dollar_volume holds; abort if any leg's quote price-impact > 5x expected.
```

Output: a printable schedule with token, per-leg amount, expected friction, cumulative volume.

### V3 — Execute

For each leg in plan:

```bash
onchainos swap execute --from <in> --to <out> --readable-amount <amt> --chain <chain> --wallet <addr> --slippage <tol>
```

After each leg:
1. Re-fetch token balance via `onchainos wallet balance --chain <c> --token-address <ca> --force` (handles "swap output dust" issue — see Edge Cases)
2. Compute realized friction for the leg
3. Update running totals
4. **Hard-stop conditions** (any of):
   - Cumulative friction usd > friction_budget_usd × 1.05 (5% overrun grace)
   - Quote on next leg returns price-impact > 5× initial estimate
   - Wallet balance falls below `100` USD (participation prize floor — see Safety)
   - User pressed Ctrl-C (CLI cancellation)

Per-leg sequencing rule: **always** sell the actual on-chain balance, NOT the value the previous swap response claimed delivered. Aggregator dust + ATA rent on Solana means the wallet balance is often ~0.01% smaller than the swap's reported `toAmount`. Selling the reported amount triggers `InstructionError[4] Custom 1` (insufficient funds).

### V4 — Report

Final fixed template (translate to user's language; do NOT improvise):

```
Volume Booster — Final Report

Target volume:        ${target} USD
Realized volume:      ${realized} USD  ({pct} of target)
Friction budget:      ${budget} USD  ({budget_pct}% of capital)
Friction realized:    ${friction} USD  ({friction_pct}% of capital, {friction_per_vol_pct}% per $1 volume)
Round trips executed: {n}
Token used:           {symbol} ({address_short})
Status:               {COMPLETED|STOPPED:reason|OVER_BUDGET}

Tx hashes (sequential):
1. {tx1}
2. {tx2}
...
```

## Safety Guardrails

<NEVER>
- ❌ Never run `execute` if the user is NOT registered for the competition. Volume completion before registration does not count.
- ❌ Never pick a token with `riskControlLevel != 1` for round-trips, even if liquidity is great.
- ❌ Never disable the friction budget cap. If the user wants more volume, increase `target_volume_usd`, not `friction_budget_pct`.
- ❌ Never round-trip through an excluded pair (stable↔stable / native↔stable / native↔wrapped-native). Trades won't count and friction is wasted.
- ❌ Never use `--force` on first call to `swap execute`. The first call is plain; only re-issue with `--force` after a confirming response.
- ❌ Never proceed below the participation-prize wallet floor ($100). Stop and report.
</NEVER>

<MUST>
- ✅ Always re-fetch on-chain balance with `--force` before selling — do not trust the prior swap's reported `toAmount`.
- ✅ Always show the plan and ask "OK to execute?" before running `execute`. The user must explicitly confirm.
- ✅ Always log every tx hash in the running report.
- ✅ Always re-quote the next leg if the previous leg's realized friction exceeds 2× the prior estimate (price regime may have shifted).
</MUST>

## Volume Estimation (when API doesn't return it directly)

`competition user-status` returns `joinStatus` but NOT cumulative volume. Two ways to estimate:

1. **Local accounting**: this skill maintains a session-local counter (sum of `fromAmount * fromToken.tokenUnitPrice + toAmount * toToken.tokenUnitPrice` across all swap responses). Reliable for trades executed in the current session.
2. **Trade history scan**: `onchainos wallet history --chain <c> --address <addr> --limit 100`, filter to swaps in competition window, sum the USD legs. Use when continuing across sessions.

**The local counter is preferred** because it ignores trades that don't qualify (excluded pairs, pre-registration trades, off-chain transfers). Persist it to `~/.onchainos/volume-booster-state.json` keyed by `(activityId, accountId)`.

## Excluded Pairs (competition rules)

> Detail: `references/excluded-pairs.md`

Per Agentic Wallet competition rules, the following do NOT count toward qualifying volume:
- stablecoin ↔ stablecoin (e.g. USDC↔USDT, USDC↔USDG)
- native ↔ stablecoin (e.g. SOL↔USDC, OKB↔USDC)
- native ↔ wrapped-native (e.g. SOL↔WSOL)
- wrapped-native ↔ stablecoin (e.g. WSOL↔USDC)

This skill **never** routes through these pairs. The aggregator may internally route via SOL/WSOL, but the user-facing trade pair (USDC↔TOKEN, SOL↔TOKEN, etc.) is what the competition ranks against, so that's fine — the rule is about the user's submitted pair, not internal route hops.

## Edge Cases

### Aggregator dust on Solana
Symptom: leg 2 simulation fails with `InstructionError[4]: Custom 1`.
Cause: swap response's `toAmount` reports the gross amount; the wallet receives `toAmount - dust` (ATA rent, route fees).
Fix: always re-read on-chain balance with `wallet balance --force` before scheduling the sell leg.

### Solana priority gas spike
Symptom: realized friction per leg jumps from 0.07% to 0.5%+.
Cause: Solana mempool congestion → priority fees auto-bid up.
Fix: pause for 30–60s, re-quote. If persistent, reduce `gas-level` (default `average` → `economic`) and accept slower confirmation.

### Token price moves between legs
Symptom: cumulative friction higher than expected even with low priceImpact reports.
Cause: token price shifted between buy and sell — the swap is fast but not instant.
Mitigation: keep round-trip size in pools where 2× the trade is < 0.1% of TVL (so MM rebalance brings price back fast). For deeper protection, run quote → execute back-to-back without yielding.

### Competition data lag
Symptom: after volume completion, `competition rank --wallet <addr>` returns `myRankInfo: null`.
Cause: backend metric pipeline delay (5–30 min typical).
Fix: this is normal. Tell the user to recheck in 30 min. Do NOT add more volume to "fix" it.

## Examples

### Example 1 — Default Solana flow

```
User: "Help me hit the trading volume requirement"

Agent:
1. Reads wallet status → logged in, account ID xxx
2. Reads competition_user_status → joined Agentic Trading Contest (chainName: X Layer + Solana hardcoded)
3. Reads wallet balance → $414 total
4. Pick token: JUP on Solana (deepest non-excluded)
5. Plan:
   - Target $1000 volume, budget 0.5% × $414 = $2.07
   - 3 round-trips (USDC×2, SOL×1) → expected $1000 vol, ~$0.40 friction
6. Print plan, ask user to confirm
7. On confirm: execute 6 swaps in sequence, verifying friction live
8. Final report: realized $1038 vol, $0.43 friction (0.10% of capital)
```

### Example 2 — Tight budget

```
User: "刷交易量但只能花 $1"
target_volume_usd = 1000
friction_budget_pct = 0.24  // $1 / $414

Plan would refuse and ask user to either lower target or raise budget;
do NOT silently degrade.
```

## Versioning

- `0.1.0` (initial): Solana support, JUP route, USDC + SOL recycle pattern, dry-run mode.
- (planned) `0.2.0`: X Layer support, USDT-X route on OKB-USDT pool.
- (planned) `0.3.0`: persistent state file, cross-session continuation.

## Acknowledgements

Built on top of:
- `onchainos` CLI — wallet, swap, token, competition commands
- `okx-agentic-wallet` — auth and balance reads
- `okx-dex-swap` — quote and execute
- `okx-dex-token` — hot-tokens and liquidity probe
- `okx-growth-competition` — registration and status

This Skill exists because it's the cheapest way to qualify for the Agentic Wallet leaderboard, given the competition's exclusion rules. It saves participants an estimated $5–20 in friction per qualification cycle compared to naïve "buy and sell anything" approaches.
