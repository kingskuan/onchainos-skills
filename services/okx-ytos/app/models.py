from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

# The four data tools YtOS exposes (mirrors the DeFi Dashboard's data layer).
Tool = Literal["wallet", "pendle_markets", "pendle_wallet", "yields"]


class YtOSRequest(BaseModel):
    # camelCase + snake_case + synonym tolerant, so a paid x402 call never 422s
    # on a minor field-name mismatch (which would waste a settlement).
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tool: Tool = Field(
        "wallet", description="Which data tool to run",
        validation_alias=AliasChoices("tool", "assistant", "action", "op"))
    address: Optional[str] = Field(
        None, description="Wallet address (for wallet / pendle_wallet)",
        validation_alias=AliasChoices("address", "wallet", "account", "addr"))
    chain: str = Field(
        "eth", description="Chain: eth|base|optimism|arbitrum|polygon|gnosis|bsc",
        validation_alias=AliasChoices("chain", "network", "chainName"))
    project: Optional[str] = Field(
        None, description="Protocol filter for yields e.g. aave-v3, lido",
        validation_alias=AliasChoices("project", "protocol"))
    symbol: Optional[str] = Field(
        None, description="Token/pool symbol filter for yields e.g. USDC",
        validation_alias=AliasChoices("symbol", "token", "asset"))
    min_tvl: float = Field(
        1_000_000, ge=0, description="Minimum pool TVL (USD) for yields",
        validation_alias=AliasChoices("min_tvl", "minTvl", "minTVL"))
    stable_only: bool = Field(
        False, description="Only stablecoin pools (yields)",
        validation_alias=AliasChoices("stable_only", "stableOnly", "stablesOnly"))
    limit: int = Field(
        20, ge=1, le=100, description="Max rows returned",
        validation_alias=AliasChoices("limit", "top", "max"))


class YtOSResponse(BaseModel):
    tool: str
    data: Dict[str, Any]
    markdown: str
    meta: Dict[str, Any] = Field(default_factory=dict)
