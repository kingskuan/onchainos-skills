#!/usr/bin/env bash
# agentic-volume-booster — reproducible demo
# Replays the May 2026 session that hit $1,038 qualifying volume on $0.43 friction.
#
# Prerequisites:
#   1. onchainos CLI installed and on PATH
#   2. Wallet logged in: `onchainos wallet login <email> --locale zh-CN`
#         then `onchainos wallet verify <code>`
#   3. Registered for the competition:
#         onchainos competition list --status 0
#         onchainos competition join --activity-id <id> --evm-wallet <addr> \
#             --sol-wallet <addr> --chain-index 196
#   4. Wallet funded: ~$100 USDC + ~3 SOL on Solana
#
# Usage:
#   ./demo.sh                # dry-run (default — quote only, no execution)
#   ./demo.sh --execute      # really swap
#
# WARNING: Exec mode broadcasts 8 real on-chain swaps. Only run on funds you
# can afford to lose. The skill's Risk Disclaimer applies.

set -euo pipefail

# --- Constants -----------------------------------------------------------------

CHAIN="solana"
WALLET_SOL="${WALLET_SOL:-J18oPVDAhSAfi7r7THzo3jDzvwKKGRL8q9uxKde6jFyB}"
USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUP="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
SOL_NATIVE="11111111111111111111111111111111"
SLIPPAGE="0.5"

EXECUTE=0
[[ "${1:-}" == "--execute" ]] && EXECUTE=1

# --- Helpers -------------------------------------------------------------------

log() { echo -e "\n[demo] $*"; }

step() {
  local label="$1" from="$2" to="$3" amount="$4"
  log "$label: $amount of $from -> $to"
  if [[ $EXECUTE -eq 0 ]]; then
    onchainos swap quote \
      --from "$from" --to "$to" \
      --readable-amount "$amount" --chain "$CHAIN" \
      | jq -r '.data[0] | "  quote: \(.toTokenAmount) (\(.toToken.tokenSymbol)), priceImpact \(.priceImpactPercent)%"'
  else
    onchainos swap execute \
      --from "$from" --to "$to" \
      --readable-amount "$amount" --chain "$CHAIN" \
      --wallet "$WALLET_SOL" --slippage "$SLIPPAGE" \
      | jq -r '.data | "  tx: \(.swapTxHash)\n  filled: \(.toAmount)"'
  fi
}

balance_of() {
  local token_addr="$1"
  onchainos wallet balance --chain "$CHAIN" --token-address "$token_addr" --force \
    | jq -r '.data.details[0].tokenAssets[0].balance // "0"'
}

# --- Pre-flight ----------------------------------------------------------------

log "Pre-flight: wallet status"
onchainos wallet status | jq '{loggedIn:.data.loggedIn, account:.data.currentAccountName}'

log "Pre-flight: competition registration"
onchainos competition user-status \
  --evm-wallet "0x0000000000000000000000000000000000000000" \
  --sol-wallet "$WALLET_SOL" \
  | jq -r '.data | "  joinStatus: \(.joinStatus), rewardStatus: \(.rewardStatus)"'

log "Pre-flight: wallet capital"
onchainos wallet balance --force \
  | jq -r '.data | "  totalUsd: $\(.totalValueUsd)"'

if [[ $EXECUTE -eq 0 ]]; then
  log "DRY RUN — no swaps will execute. Use --execute to broadcast."
fi

# --- Phase 1: Calibration ($30 round-trip) -------------------------------------

log "===== Phase 1 — Calibration =====
"
step "Cal-1 buy"  "$USDC" "$JUP"  "30"

if [[ $EXECUTE -eq 1 ]]; then
  CAL_JUP="$(balance_of "$JUP")"
  log "On-chain JUP balance: $CAL_JUP (NOT the swap response's toAmount — that includes dust)"
  step "Cal-2 sell" "$JUP" "$USDC" "$CAL_JUP"
fi

# --- Phase 2: Round 1 ($95 USDC) ----------------------------------------------

log "===== Phase 2 — R1 ($95 USDC) ====="
step "R1-1 buy"  "$USDC" "$JUP" "95"

if [[ $EXECUTE -eq 1 ]]; then
  R1_JUP="$(balance_of "$JUP")"
  step "R1-2 sell" "$JUP" "$USDC" "$R1_JUP"
fi

# --- Phase 3: Round 2 ($94 USDC, recycled) ------------------------------------

log "===== Phase 3 — R2 ($94 USDC) ====="
step "R2-1 buy"  "$USDC" "$JUP" "94"

if [[ $EXECUTE -eq 1 ]]; then
  R2_JUP="$(balance_of "$JUP")"
  step "R2-2 sell" "$JUP" "$USDC" "$R2_JUP"
fi

# --- Phase 4: Round 3 ($300 SOL) ----------------------------------------------

log "===== Phase 4 — R3 ($300 SOL) ====="
step "R3-1 buy"  "$SOL_NATIVE" "$JUP" "3.4"

if [[ $EXECUTE -eq 1 ]]; then
  R3_JUP="$(balance_of "$JUP")"
  step "R3-2 sell" "$JUP" "$SOL_NATIVE" "$R3_JUP"
fi

# --- Final report --------------------------------------------------------------

log "===== Final report ====="
onchainos wallet balance --force \
  | jq -r '.data | "Wallet end balance: $\(.totalValueUsd) total
  USDC: \(.details[0].tokenAssets[] | select(.symbol == "USDC") | .balance)
  SOL:  \(.details[0].tokenAssets[] | select(.symbol == "SOL")  | .balance)"'

log "Volume booster session complete."
log "Expected: ~\$1,038 qualifying volume, ~\$0.43 net friction"
log "Verify rank in 5-30 min:"
log "  onchainos competition rank --activity-id <id> --wallet $WALLET_SOL --sort-type 1"
