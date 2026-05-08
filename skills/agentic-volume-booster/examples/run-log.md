# Real-world Run Log — Solana, May 2026

This is a verbatim execution log of `agentic-volume-booster` on a live Agentic Wallet account during the OKX Agentic Trading Contest (activity-id: `agentic-trading`, chain: Solana + X Layer).

**Headline result**: hit $1,000+ qualifying volume with **0.10% capital friction** — 5× under the 0.5% budget cap.

## Session metadata

| Field | Value |
|---|---|
| Wallet Solana address | `J18oPVDAhSAfi7r7THzo3jDzvwKKGRL8q9uxKde6jFyB` |
| Wallet EVM address | `0x9022ea0d686b521a0b92448fd77c288ab1766fb1` |
| Account name | Account 1 |
| Account ID | `77f413c3-ddee-4f77-9f51-f630b41962ed` |
| Competition | Agentic Trading Contest (`shortName: agentic-trading`, prize 50,000 USDC) |
| Chain | Solana (chainIndex 501) |
| Route token | JUP (`JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN`) |
| Route reasoning | Deepest USDC-side liquidity ($4M+ aggregate), 0.05% LP fee on best pool, 9-month-old, riskControlLevel 1, NOT in excluded set |
| Starting capital | $414.42 (99.104 USDC + 3.572 SOL) |
| Target volume | $1,000 |
| Friction budget | $2.07 (0.5% of capital) |
| Slippage tolerance | 0.5% per leg |

## Execution timeline

### Phase 1 — Calibration ($30 USDC ↔ JUP round-trip)

Goal: validate quoted friction estimate with a small live trade before scaling.

| Leg | From | To | Amount | Tx Hash |
|---|---|---|---|---|
| Cal-1 | 30.000 USDC | 146.345 JUP | $30.00 | `3KF4yDYey1gwuaMnryoCR7Ny3qeDif8MG3MTtxeBeDcSTit9p6Dn2VkSaYdoAuvTfGEkmGnvHvB7HhNrz4dRdjn8` |
| Cal-2 | 146.335 JUP | 29.989 USDC | $30.00 | `2Vi9Gs5Z75NtDUZrp9eVFy5WWfwivC4sdVZmgPQzoQJMQ34K3ptNwSqqpSWKrdj3ARb1M4yX6rmBESwtXTacBUiN` |

Net: spent 30.000 USDC, recovered 29.989 USDC → **friction $0.011 = 0.018% of $60 volume**.

> ⚠️ Cal-2 first attempt simulation-failed with `InstructionError[4] Custom 1` because we tried to sell the swap response's reported `toAmount: 146.345` JUP. The wallet's actual on-chain balance was 146.335 (10K dust evaporated to ATA rent / aggregator fees). Re-fetching balance with `wallet balance --force` and selling the actual amount succeeded. **This is the canonical Solana SPL dust failure mode — the skill's Error Handling table documents it**.

### Phase 2 — Round 1 (USDC ↔ JUP, $95)

| Leg | From | To | Amount | Tx Hash |
|---|---|---|---|---|
| R1-1 | 95.000 USDC | 464.317 JUP | $95.00 | `4omrqHxU9urVu842kQjhZKRY3wGUaPqPXmFnGvxKcsGvT8Urok3pzXh3mxboXwvhvbLqsmsjy7sCyQSxbD9nru1z` |
| R1-2 | 464.317 JUP | 94.994 USDC | $94.99 | `5sQvPBusNroHW22CymwE4s2dTL1E61ziQE7km9weywTLpM3QhheLWTUmMMmukbkJE73PhoJxx2fMunBVrRjHpgeD` |

Net: friction **$0.006 = 0.0032% of $190 volume** (best round-trip of the session).

### Phase 3 — Round 2 (USDC ↔ JUP, $94, recycled)

| Leg | From | To | Amount | Tx Hash |
|---|---|---|---|---|
| R2-1 | 94.000 USDC | 459.236 JUP | $94.00 | `4W48ZxXgv61WVRAJXEGymHJH2TfPEhaHSBMRDsZAE2b216idbsSddW9Ttg2vhqCQAbHVxspdHnqHe3Nhu4SAuW4z` |
| R2-2 | 459.198 JUP | 93.960 USDC | $93.96 | `3rgjAJPbQisYAqBaW4PCxt11qHJ169DhUqukRtmKaFqz1srWrY9VvRQSkrt9Dup34p5SAs56pW1eY1K2VCyvwocY` |

Net: friction **$0.040 = 0.021% of $187.96 volume**. Slightly higher than R1; price impact on R2-1 was -0.04 (vs R1-1's 0).

### Phase 4 — Round 3 (SOL ↔ JUP, $300)

| Leg | From | To | Amount | Tx Hash |
|---|---|---|---|---|
| R3-1 | 3.400 SOL | 1467.448 JUP | $300.25 | `3NzBCh6pQbWovF3TkVampxLm3Pssi9cvBDab1xBVBnyaNuNeieDr18AuWng6VtDvu26KoJyCBf4zKoPnHy53FCta` |
| R3-2 | 1467.448 JUP | 3.398597 SOL | $300.13 | `2dQpkMKfGSSMUJd9Q3PeSsr9cuJyjZakNDT51bPJ57A5ErRrU5DZq1ob4R6vCiiQX88q7jy5bGCzyLoyNeDWR8dJ` |

Net: friction **$0.124 = 0.021% of $600.38 volume**. Larger trade size → larger absolute friction but same percentage rate as R2.

## Final accounting

| Metric | Value |
|---|---|
| Cumulative qualifying volume | **$1,038** (104% of $1,000 target) |
| Wallet at session end | $413.99 (98.891 USDC + 3.568 SOL) |
| **Net realized friction** | **$0.43** |
| Friction as % of capital | **0.10%** (vs 0.50% budget) |
| Friction as % of volume | **0.041%** |
| Round-trips executed | 4 (1 calibration + 3 production) |
| Total tx count | 8 swaps |
| Average per-leg gas (Solana priority) | ~$0.05 |
| Plan completion status | COMPLETED |

## Friction breakdown (per round-trip, ranked best to worst)

| Round | Volume | Friction USD | Friction % of volume |
|---|---|---|---|
| R1 (USDC↔JUP $95) | $189.99 | $0.006 | 0.0032% |
| Cal (USDC↔JUP $30) | $59.99 | $0.011 | 0.0184% |
| R3 (SOL↔JUP $300) | $600.38 | $0.124 | 0.0207% |
| R2 (USDC↔JUP $94) | $187.96 | $0.040 | 0.0213% |

The "USDC↔JUP $95" round was the cheapest because aggregator routing happened to land on the best Orca Whirlpool tier with zero priority gas spike.

## Competition status post-execution

```bash
$ onchainos competition rank --activity-id 113 --wallet J18oP... --sort-type 1
{
  "myRankInfo": null,
  "rankUpdateTime": 1778213700595,
  "allRankInfos": [/* top 3 entries */]
}
```

`myRankInfo: null` is **expected** — the backend metric pipeline takes 5–30 minutes to ingest fresh trades. The skill's Error Handling table documents this as "competition data lag — recheck in 30 min, do NOT add more volume to fix it".

## What this proves

1. **Strategy completeness**: end-to-end flow from `wallet status` → competition status check → token selection → quote → execute → re-verify balance → next leg → final report. No manual steps required after plan confirmation.
2. **Risk control**: $2.07 budget held — **realized $0.43 was 79% under budget**.
3. **Execution reliability**: handled the canonical Solana SPL dust failure (Cal-2 first attempt) without aborting. Recovered cleanly by re-fetching on-chain balance.
4. **User safety**: every leg used standard `wallet send / swap execute` with TEE signing — never asked the user for keys, never exposed the active token amount in plaintext.
5. **Observability**: per-leg friction logged + final report emitted with all 8 tx hashes. All txs verifiable on Solana explorer.

## Reproduce

```sh
export ONCHAINOS_HOME="$PWD/.onchainos"
onchainos wallet status                                         # check auth
onchainos competition user-status \
  --evm-wallet 0x9022ea0d686b521a0b92448fd77c288ab1766fb1 \
  --sol-wallet J18oPVDAhSAfi7r7THzo3jDzvwKKGRL8q9uxKde6jFyB     # confirm joinStatus=1

# Phase 1 — calibration
onchainos swap execute --from EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v \
  --to JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN \
  --readable-amount 30 --chain solana \
  --wallet J18oPVDAhSAfi7r7THzo3jDzvwKKGRL8q9uxKde6jFyB --slippage 0.5

# ... (re-fetch balance, sell back, repeat for 3 production rounds)
```

See `examples/demo.sh` for the full sequence.
