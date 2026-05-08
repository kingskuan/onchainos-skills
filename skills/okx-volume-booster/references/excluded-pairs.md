# Excluded Pairs Reference

Pairs that do NOT count toward Agentic Wallet competition qualifying volume.

## Source

OKX Agentic Wallet trading competition rules, in the `competition_detail` response under `tabConfigs[].tabDetails[]`:

> Swaps between stablecoins, native tokens (SOL, OKB), and wrapped native tokens (WSOL, WOKB) do not count toward PnL% or qualifying trading volume, including but not limited to SOL-USDC, SOL-WSOL and USDT-USDC.

## Interpretation

A trade `A → B` is **excluded** iff both A and B are in the union set `{stablecoins} ∪ {natives} ∪ {wrapped-natives}` for the chain.

A trade `A → B` is **counted** if at least one of A or B is outside that union — i.e. one side is a regular token (memes, governance tokens, utility tokens, etc.).

## Per-chain enumeration

### Solana (chain index 501)

| Symbol | Type | Address |
|--------|------|---------|
| SOL | native | `11111111111111111111111111111111` |
| WSOL | wrapped-native | `So11111111111111111111111111111111111111112` |
| USDC | stablecoin | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` |
| USDT | stablecoin | `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB` |
| USDG | stablecoin | (chain-specific Global Dollar) |
| USDS | stablecoin | (Sky / Maker stable) |
| USDH | stablecoin | (Hubble) |
| PYUSD | stablecoin | (PayPal USD) |
| FDUSD | stablecoin | (First Digital USD) |
| JupUSD | stablecoin | `JuprjznTrTSp2UFa3ZBUFgwdAmtZCq4MQCwysN55USD` |

**Excluded pair examples on Solana**:
- USDC ↔ USDT (stable ↔ stable)
- SOL ↔ USDC (native ↔ stable)
- SOL ↔ WSOL (native ↔ wrapped)
- WSOL ↔ USDC (wrapped ↔ stable)
- USDT ↔ JupUSD (stable ↔ stable)

**NOT excluded (counts)**:
- USDC ↔ JUP (stable ↔ token)
- SOL ↔ JUP (native ↔ token)
- BONK ↔ JUP (token ↔ token)
- USDC ↔ JitoSOL (stable ↔ liquid-staking-derivative — not a wrapped native!)

### X Layer (chain index 196)

| Symbol | Type | Address |
|--------|------|---------|
| OKB | native | `0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` |
| WOKB | wrapped-native | `0xe538905cf8410324e03A5A23C1c177a474D59b2b` |
| USDC | stablecoin | `0x74b7f16337b8972027f6196a17a631ac6de26d22` |
| USDT | stablecoin | `0x1e4a5963abfd975d8c9021ce480b42188849d41d` |

### Other chains

Not supported in this skill version. Each chain has its own native + wrapped + stablecoin set.

## Edge cases

### Liquid staking derivatives

JitoSOL, mSOL, bSOL on Solana are LSDs — they represent staked SOL but are NOT "wrapped native" in the rule's sense. The rule's "wrapped native" specifically means WSOL (1:1 wrap of SOL with no yield mechanic).

Therefore:
- SOL ↔ JitoSOL — **counts** (token-to-native pair, JitoSOL is a token)
- USDC ↔ JitoSOL — **counts** (stable ↔ token)
- WSOL ↔ JitoSOL — **counts** (wrapped-native ↔ token)

### Bridged stablecoins

USDC.e, USDT.e (bridged variants on some chains) are stablecoins for this purpose. The rule says "stablecoins" generally, not "natively-issued USDC".

### Aggregator route hops

The user's submitted trade pair is `USDC → JUP`. The Jupiter aggregator may internally route via `USDC → wSOL → JUP`. The intermediate `USDC → wSOL` hop happens inside the aggregator's transaction; the user's trade pair as recorded by the competition backend is `USDC → JUP`, which counts.

This is observable via `swap quote` response — the `dexRouterList[]` shows the internal hops. The competition backend reads only the user-facing `from / to` of the swap, not the internal route.

### New stablecoin launches

When a new stablecoin launches (e.g. JupUSD March 2026), it should be added to this list defensively. If unsure whether a new asset is "stable enough" to be in the excluded set:
- Symbol contains "USD" (case-insensitive) AND price stable within ±0.5% of $1 → treat as stable.
- Symbol contains "EUR" / "GBP" / etc. → treat as stable (foreign-currency pegs).
- LSDs (JitoSOL, etc.) → NOT stable; counts.

## How the skill enforces this

```python
def is_excluded_pair(from_token, to_token, chain):
    excluded = EXCLUDED_SETS[chain]
    return (from_token in excluded) and (to_token in excluded)

def validate_route(plan):
    for leg in plan.legs:
        if is_excluded_pair(leg.from_token, leg.to_token, plan.chain):
            raise PlanError(
                f"Leg {leg.id} is an excluded pair ({leg.from_token}→{leg.to_token}) "
                f"and would not count toward competition volume."
            )
```

Validation happens at `plan` time and again at `execute` time (in case the token set was updated between).

## When the rule changes

Tracking the source of truth:
- `competition_detail.tabConfigs[].tabDetails[]` (read at session start)
- Compare returned text against the embedded rule string here.
- If different, prefer the API; log a warning to update this doc.

## Quick test

Two trades to verify the agent reads this correctly:

```
1. USDC → JUP → USDC  (counts: stable↔token in both directions, $190 volume)
2. USDC → SOL → USDC  (does NOT count: native↔stable, both directions excluded)
```

If the user's `competition_user_status` shows volume after (1) but not (2), the rule is being enforced as documented.
