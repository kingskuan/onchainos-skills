# Friction Model

How `okx-volume-booster` estimates and tracks the cost of completing a target trading volume.

## Definitions

- **Volume**: cumulative USD amount swapped, summed across all qualifying legs (both buys and sells count).
- **Friction**: net loss in wallet USD value caused by executing the round-trip plan, excluding directional price movement of held tokens.
- **Capital**: total wallet USD at session start.

Critically, the volume budget and friction budget are **decoupled**:
- Volume is the throughput target (e.g. $1,000).
- Friction is the cost cap (e.g. 0.5% of capital).

A naïve "buy a meme and sell it" approach can hit volume but burn 2–5% of capital. The skill's job is to hit volume with friction far below 1%.

## One-way friction decomposition

For a single swap from token A to token B:

```
friction_one_way = LP_fee + price_impact + slippage_realized + tx_gas_usd
```

Where:
- **LP fee**: the AMM pool's `liquidityProviderFeePercent`, paid to LPs.
- **Price impact**: price moves against you because your trade consumes pool depth. Reported by `onchainos swap quote` as `priceImpactPercent`.
- **Slippage realized**: the gap between `quote.toAmount` and the actual on-chain delivered amount, due to between-quote-and-fill price movement. Bounded by the user-set `--slippage` tolerance.
- **Tx gas**: network priority fee. Solana ~$0.001–0.01; EVM mainnet far higher.

For a round-trip (buy + sell):

```
friction_round_trip = 2 × friction_one_way + dust
```

Where **dust** is the tiny token amount that disappears between the swap output and the wallet's actual receipt. Empirically observed at 0.005–0.05% of trade size on Solana SPL tokens (ATA rent, aggregator route fees).

## Empirical baselines (Solana, May 2026)

| Pair | One-way | Round-trip (incl. dust) | Pool TVL | LP fee |
|------|---------|--------------------------|----------|--------|
| USDC ↔ JUP | 0.07% | 0.14–0.20% | $4M+ aggregate | 0.05% (best pool) |
| SOL ↔ JUP | 0.10% | 0.20–0.30% | $1.4M+ | 0.05% (best pool) |
| USDC ↔ HANTA | 0.30% | 0.50–0.70% | $950K | 0.25% (best pool) |
| USDC ↔ BURNIE | 0.20% | 0.40–0.60% | $1.28M | 0.20% |

JUP is the empirical winner because its USDC-side liquidity is unusually deep for its market cap (Jupiter's own DEX aggregator self-supports the pair).

## Trade-size scaling

Price impact scales superlinearly with trade size relative to pool depth:

```
price_impact ≈ (trade_size_usd / pool_tvl_usd)^1.2 × constant
```

Practical implications:
- A $100 trade on a $1M pool → price impact ~0.02–0.05%.
- A $1,000 trade on the same pool → price impact ~0.3–0.5%.
- A $5,000 trade on the same pool → price impact 2–5%, blows the friction budget.

The skill's planner caps single-leg size at `min(round_size, capital × 0.8, pool_tvl × 0.005)` — i.e. never more than 0.5% of the target pool's TVL.

## Friction ratchet

The skill tracks a **friction ratchet** during execution: realized friction per leg is logged, and the running total is compared against the budget.

```
realized_friction_per_dollar_volume_t = (capital_start - capital_t) / cumulative_volume_t
```

If `realized_friction_per_dollar_volume_t > 2 × initial_estimate` for two consecutive legs, the planner will:
1. Stop and re-quote with current pool state.
2. If the new quote shows `priceImpactPercent > 5 × initial_quote`, abort the remaining schedule and report.

This catches both:
- A pool that's gotten thinner (someone removed liquidity).
- Solana mempool congestion driving up priority fees.

## How the budget cap is enforced

After every leg:

```
remaining_budget = friction_budget_usd - cumulative_friction_usd
remaining_volume_target = target_volume_usd - cumulative_volume_usd
required_friction_per_dollar = remaining_budget / remaining_volume_target
```

If `required_friction_per_dollar < empirical_friction_per_dollar × 0.7` — i.e. completing the remaining target would push friction over budget even at the empirical rate — the skill stops and reports.

## Why 0.5% capital, not 5% volume

Two possible budget framings:
1. % of volume → "lose less than X% of every dollar I trade" → friction scales with volume. Stable.
2. % of capital → "lose less than Y% of my wallet" → friction caps absolutely. Less efficient at high volumes but matches user intuition.

Most users mean (2) when they say "0.5%". The skill defaults to (2). To use (1), pass `--friction-budget-pct-of-volume` instead.

## Reporting

Every report exposes:
- **Capital-percent friction**: friction_usd / capital_usd. The number users actually care about.
- **Volume-percent friction**: friction_usd / volume_usd. Useful for comparing strategies.
- **Per-leg breakdown**: lets the user see if any single leg ate the budget.

## Known limitations

- **Cross-session continuation**: friction tracked across sessions requires reading on-chain trade history, which loses the "qualifying vs not-qualifying" distinction. Workaround: persist session state to `~/.onchainos/volume-booster-state.json`.
- **MEV / sandwich attacks**: not modeled. Solana JUP via Jupiter has Jito bundle protection by default; smaller pools may not. Skill warns when pool TVL < $200K.
- **Stablecoin depeg**: if USDC depegs mid-session, the friction model breaks. Skill checks `tokenUnitPrice` deviation > 1% and aborts.
