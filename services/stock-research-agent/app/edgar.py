"""SEC EDGAR client — official, free, no API key.

Pulls US-GAAP fundamentals from the EDGAR `companyfacts` API and shapes them
into 5-year financial statements plus health/valuation inputs. Everything here
works from official filings, so it is reliable and reproducible.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

# SEC requires a descriptive User-Agent with contact info.
UA = "stock-research-agent/0.1 (contact: set-your-email@example.com)"
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}

_TICKER_MAP: dict[str, dict] | None = None
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 60 * 60 * 6  # 6h


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, val: Any):
    _CACHE[key] = (time.time(), val)


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    r = await client.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


async def load_ticker_map(client: httpx.AsyncClient) -> dict[str, dict]:
    """ticker (upper) -> {cik, title}. Cached in-process."""
    global _TICKER_MAP
    if _TICKER_MAP is not None:
        return _TICKER_MAP
    data = await _get_json(client, "https://www.sec.gov/files/company_tickers.json")
    m: dict[str, dict] = {}
    for row in data.values():
        m[row["ticker"].upper()] = {
            "cik": str(row["cik_str"]).zfill(10),
            "title": row["title"],
        }
    _TICKER_MAP = m
    return m


async def resolve_cik(client: httpx.AsyncClient, ticker: str) -> dict | None:
    m = await load_ticker_map(client)
    return m.get(ticker.upper())


async def company_facts(client: httpx.AsyncClient, cik: str) -> dict:
    key = f"facts:{cik}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    data = await _get_json(client, url)
    _cache_put(key, data)
    return data


# ── concept extraction ────────────────────────────────────────────────────

# Ordered fallbacks: first concept that has data wins.
CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "liabilities": ["Liabilities"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "short_term_debt": ["DebtCurrent", "ShortTermBorrowings"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "dep_amort": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ],
    "shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}


def _annual_series(facts: dict, concept: str) -> dict[int, float]:
    """Return {fiscal_year: value} from annual (FY, 10-K) datapoints."""
    node = facts.get("facts", {}).get("us-gaap", {}).get(concept)
    if not node:
        return {}
    out: dict[int, tuple[str, float]] = {}  # fy -> (end_date, val)
    for unit_rows in node.get("units", {}).values():
        for row in unit_rows:
            if row.get("fp") != "FY":
                continue
            if row.get("form") not in ("10-K", "10-K/A", "20-F", "40-F"):
                continue
            fy = row.get("fy")
            end = row.get("end")
            val = row.get("val")
            if fy is None or val is None or end is None:
                continue
            prev = out.get(fy)
            # keep the datapoint with the latest period end for that FY
            if prev is None or end > prev[0]:
                out[fy] = (end, float(val))
    return {fy: v for fy, (e, v) in out.items()}


def series_for(facts: dict, key: str) -> dict[int, float]:
    for concept in CONCEPTS[key]:
        s = _annual_series(facts, concept)
        if s:
            return s
    return {}


def latest_shares_outstanding(facts: dict) -> float | None:
    """Most recent shares outstanding from dei (instant, most reliable)."""
    node = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding")
    best: tuple[str, float] | None = None
    if node:
        for unit_rows in node.get("units", {}).values():
            for row in unit_rows:
                end, val = row.get("end"), row.get("val")
                if end and val:
                    if best is None or end > best[0]:
                        best = (end, float(val))
    if best:
        return best[1]
    # fallback: us-gaap CommonStockSharesOutstanding
    node = facts.get("facts", {}).get("us-gaap", {}).get("CommonStockSharesOutstanding")
    if node:
        for unit_rows in node.get("units", {}).values():
            for row in unit_rows:
                end, val = row.get("end"), row.get("val")
                if end and val:
                    if best is None or end > best[0]:
                        best = (end, float(val))
    return best[1] if best else None


def latest(series: dict[int, float]) -> float | None:
    if not series:
        return None
    return series[max(series)]
