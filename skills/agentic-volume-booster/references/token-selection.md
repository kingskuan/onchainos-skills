# Token Selection Algorithm

How `agentic-volume-booster` picks the optimal token to round-trip through.

## Goal

Find the token that minimizes `friction_per_dollar_volume` while staying inside competition exclusion rules and risk constraints.

## Inputs

- Target chain (e.g. `solana`, `xlayer`)
- Excluded symbols (chain-specific stable + native + wrapped sets — see `excluded-pairs.md`)
- Capital and target round-trip size
- Risk tolerance (default: `riskControlLevel == 1` only)

## Output

A single `(chain, token_address, route_pair)` tuple plus the rationale, e.g.:

```json
{
  "chain": "solana",
  "tokenAddress": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
  "tokenSymbol": "JUP",
  "routePair": "USDC↔JUP",
  "expectedFrictionPerVolume": 0.0009,
  "rationale": "Deepest non-excluded liquidity on Solana ($4M+ aggregate USDC-routed); 0.05% LP fee on best pool; 9-month-old, riskControlLevel=1"
}
```

## Algorithm

```
1. EXCLUDE_SET = read from references/excluded-pairs.md for the chain
2. CANDIDATES = onchainos token hot-tokens
   --chain <chain>
   --liquidity-min 200000
   --volume-min 500000
   --market-cap-min 1000000
   --limit 30

3. For each c in CANDIDATES:
     skip if c.tokenSymbol in EXCLUDE_SET
     skip if c.riskControlLevel != 1
     skip if c.top10HoldPercent > 50
     skip if c.tokenSymbol matches /^(usd|usdt|usdc|usdg|...)/i  (defensive, in case hot-tokens didn't exclude)

4. For each surviving c, run:
     pools = onchainos token liquidity --address c.address --chain c.chain
     best_pool = argmax(pools, key=p.liquidityUsd / (p.liquidityProviderFeePercent + 0.001))
     c.score = best_pool.liquidityUsd / (best_pool.liquidityProviderFeePercent + 0.001)
     c.bestPool = best_pool

5. WINNER = argmax(CANDIDATES, key=score)

6. Sanity check WINNER:
     - liquidityUsd > 10 × planned_max_round_size
     - LP fee < 1.0%
     - At least 2 distinct pools (so we can survive one pool de-listing)

7. If no winner survives, broaden filters one tier (--liquidity-min 100000, --market-cap-min 500000) and retry once. If still none, raise SkillError("no viable round-trip token on <chain>; try a different chain or wait for liquidity").
```

## Why deepest pool, not lowest LP fee alone

A 0.01% LP fee pool with $50K TVL is worse than a 0.10% LP fee pool with $5M TVL once trade size hits ~$100. Price impact dominates LP fee at small TVL.

The score `liquidityUsd / (LP_fee_pct + 0.001)` blends both:
- A $5M / 0.05% pool scores 100,000.
- A $500K / 0.005% pool scores 91,000.
- A $50K / 0.001% pool scores 24,500.

The "+0.001" floor prevents divide-by-zero on rare 0%-fee pools (which exist on some Solana CLOBs like Orca SOL-mSOL).

## Per-chain notes

### Solana

**Default winner**: JUP (Jupiter governance, contract `JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN`).

Why JUP:
- $4M+ aggregate USDC-routed liquidity (Meteora + Orca + Raydium + PancakeSwap)
- 0.05% LP fee on Orca Whirlpools — lowest among non-stable major Solana tokens
- Established (≥9 months at time of writing); riskControlLevel 1
- Not in excluded set (it's a token, not a stable / native / wrapped-native)

Backup candidates on Solana (in order):
1. JTO (Jito governance) — slightly thinner liquidity
2. WIF — meme but $400M+ MC, deep liquidity
3. BONK — large MC, but trades through SOL-only pools more often (still counts)

### X Layer

(Pending — most X Layer tokens have thin liquidity. Likely default to OKB-quoted routes through a small set of community tokens.)

### Other chains

Not supported in v0.1. The competition currently runs on Solana + (chainName from competition_detail), so other chains are out of scope.

## Refresh policy

Token selection is **cached for the session**. The skill does not re-pick mid-execution unless:
- The current winner's `priceImpactPercent` on a quote exceeds 5× the initial estimate (suggests pool changed).
- A leg returns the `riskControlLevel != 1` flag (suggests reclassification).

Re-picking mid-execution would orphan the position from the previous leg's output token.

## Excluded set construction

For Solana (chain index 501):

```
NATIVE = ["SOL"]
WRAPPED_NATIVE = ["WSOL"]  // 11111111111111111111111111111111 → So111...
STABLES = ["USDC", "USDT", "USDS", "USDG", "USDH", "PYUSD", "FDUSD", "DAI"]
EXCLUDE_SET = NATIVE ∪ WRAPPED_NATIVE ∪ STABLES
```

For X Layer:

```
NATIVE = ["OKB"]
WRAPPED_NATIVE = ["WOKB"]
STABLES = ["USDC", "USDT", "USDS"]
EXCLUDE_SET = NATIVE ∪ WRAPPED_NATIVE ∪ STABLES
```

The set is hardcoded because the OKX competition rules enumerate them explicitly. New stablecoin launches (e.g. JupUSD on Solana, March 2026) require an update to the set.

## Why not just trade SOL directly?

User trades SOL ↔ TOKEN are NOT excluded (TOKEN is in the OK set). But internally:

- SOL → JUP via Jupiter aggregator routes through wSOL pools.
- Each route hop is internal; the user-facing pair is `SOL↔JUP`, which the competition treats as a token trade and counts.

So **SOL pair is fine for volume**. The skill prefers USDC pairs by default only because USDC is more naturally "neutral" — using SOL for round-trips means market exposure to SOL price movement between buy and sell.

## Worked example (Solana, May 2026)

```
Capital: $414
Target volume: $1000
Friction budget: $2.07 (0.5% of capital)
Round trips: 3

Plan:
  1. USDC → JUP → USDC, $95 each direction → vol $190, friction ~$0.05
  2. USDC → JUP → USDC, $95 (recycled)        → vol $190, friction ~$0.05
  3. SOL  → JUP → SOL,  $300 each direction  → vol $600, friction ~$0.30
  Total: $980 volume, ~$0.40 friction

Selection rationale:
  - JUP scored 80,000 (best pool $346K / 0.005)
  - HANTA scored 19,000 (best pool $346K / 0.0025) -- skipped: bundle 13%, LP burn only 8.9%
  - PUMP scored 446,000 -- HIGHER than JUP -- but skipped: top10HoldPercent 75% > 50%

Final pick: JUP, USDC↔JUP and SOL↔JUP routes.
```

## Failure modes

### "No viable token"
Returned when the candidate list is empty after filtering. Causes:
- Chain has no qualifying tokens (rare on Solana, common on smaller chains).
- `--risk-filter` is filtering too aggressively.
- Liquidity thresholds too high for current market state.

User-facing message:
> No viable round-trip token on this chain right now. Either wait for liquidity to recover, or pass `--route-token <address>` to override the auto-pick.

### "Pool too shallow for plan"
Returned when the chosen token's best pool has `liquidityUsd < 10 × round_size`. Even if it's the deepest available, it'd blow the friction budget on the planned trade size.

User-facing message:
> The deepest non-excluded pool on this chain ({pool} at ${tvl}) is too shallow for a ${round_size} round trip. Either reduce trade size (raise `max_rounds` to spread across more legs) or skip this competition.

### "Wrapped native confusion"
Some chains return both `WSOL` and `So111...` as variants of wrapped SOL. The skill canonicalizes to the contract address, not the symbol, when checking excluded set membership.
