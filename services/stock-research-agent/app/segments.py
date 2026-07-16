"""Segment / disaggregated-revenue extractor.

The per-product and per-geography revenue breakdown lives in the 10-K's
dimensional XBRL, which the `companyfacts` feed strips out. This module pulls it
from the filing's rendered financial-statement tables (the SEC "R-files"):

    submissions API  → latest 10-K accession
    FilingSummary.xml → locate the Disaggregation / Reportable-Segment / Geography reports
    R{n}.htm          → parse the detail table into {category: {fiscal_year: net_sales}}

Best-effort and defensive: any failure degrades to `available: false` so the
core research payload never breaks. Tuned on the common Apple-style layout;
companies that structure filings differently may return partial buckets.
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .edgar import HEADERS

_CACHE: dict[str, tuple[float, Any]] = {}
_TTL = 60 * 60 * 12


def _num(s: str) -> float | None:
    s = s.strip().replace("$", "").replace(",", "").replace("\xa0", "").strip()
    if not s or s in ("—", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _fiscal_year(datestr: str) -> str | None:
    m = re.search(r"(\d{4})", datestr)
    return m.group(1) if m else None


def _clean_category(label: str) -> str:
    # "Americas | Operating segments" -> "Americas"; "iPhone" -> "iPhone"
    return re.split(r"\s*\|\s*", label)[0].strip()


# rows that are line-item labels, never category headers
_LINE_ITEMS = re.compile(
    r"^(net sales|revenue|cost of sales|gross margin|research and development|"
    r"selling|general and admin|operating income|depreciation|portion of|"
    r"\[line items\]|disaggregation of revenue|segment reporting)",
    re.I,
)


def parse_details_table(html: str, in_millions_default: bool = True) -> dict[str, Any]:
    """Parse an R-file details table into {category: {fy: net_sales}}."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return {}
    scale = 1_000_000 if in_millions_default else 1
    title = table.get_text(" ", strip=True)[:200]
    if re.search(r"in thousands", title, re.I):
        scale = 1_000
    elif re.search(r"in billions", title, re.I):
        scale = 1_000_000_000

    years: list[str] = []
    out: dict[str, dict[str, float]] = {}
    current: str | None = None

    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        cells = [c for c in cells if c != ""]
        if not cells:
            continue
        # header row with the period dates
        if not years:
            dates = [_fiscal_year(c) for c in cells if re.search(r"\d{4}", c)]
            dates = [d for d in dates if d]
            if dates and any(re.search(r"[A-Za-z]{3}\.?\s*\d", c) for c in cells):
                years = dates
                continue
        label = cells[0]
        values = [_num(c) for c in cells[1:]]
        has_nums = any(v is not None for v in values)

        if not has_nums:
            # a lone label → category header (unless it's a known line item).
            # Ignore anything before the period-header row (that's the title).
            if years and not _LINE_ITEMS.match(label) and "details)" not in label.lower():
                current = _clean_category(label)
            continue

        # a "Net sales" / "Revenue" line → attribute to current category
        if re.match(r"^(net sales|revenue|total net sales)", label, re.I):
            if current is None:
                current = "Total"
            nums = [v for v in values if v is not None]
            if years and nums:
                rec = {}
                for i, y in enumerate(years):
                    if i < len(nums) and nums[i] is not None:
                        rec[y] = nums[i] * scale
                if rec:
                    out[current] = rec
    # drop the grand total pseudo-category if real ones exist
    if len(out) > 1 and "Total" in out:
        out.pop("Total", None)
    return out


async def _get(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        return r.text
    except Exception:  # noqa: BLE001
        return None


async def _latest_10k(client: httpx.AsyncClient, cik: str) -> dict | None:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    txt = await _get(client, url)
    if not txt:
        return None
    import json

    d = json.loads(txt)
    r = d["filings"]["recent"]
    for form, acc, date in zip(r["form"], r["accessionNumber"], r["filingDate"]):
        if form == "10-K":
            return {"accession": acc.replace("-", ""), "date": date}
    return None


async def segments(client: httpx.AsyncClient, cik: str) -> dict[str, Any]:
    key = f"seg:{cik}"
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < _TTL:
        return hit[1]

    result: dict[str, Any] = {"available": False}
    filing = await _latest_10k(client, cik)
    if not filing:
        result["reason"] = "no 10-K found"
        _CACHE[key] = (time.time(), result)
        return result

    cik_int = str(int(cik))
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{filing['accession']}"
    fs = await _get(client, f"{base}/FilingSummary.xml")
    if not fs:
        result["reason"] = "no FilingSummary"
        _CACHE[key] = (time.time(), result)
        return result

    reports: list[tuple[str, str]] = []
    for m in re.finditer(r"<Report[^>]*>(.*?)</Report>", fs, re.S):
        blk = m.group(1)
        sn = re.search(r"<ShortName>(.*?)</ShortName>", blk, re.S)
        hf = re.search(r"<HtmlFileName>(.*?)</HtmlFileName>", blk, re.S)
        if sn and hf:
            import html as _html

            reports.append((hf.group(1), _html.unescape(sn.group(1))))

    used: set[str] = set()

    def pick(patterns: list[str]) -> str | None:
        # try patterns in priority order; prefer a "(Details)" report; never
        # reuse a report already claimed by an earlier bucket.
        for pat in patterns:
            cands = [
                (f, n)
                for f, n in reports
                if re.search(pat, n, re.I) and f not in used
            ]
            det = [c for c in cands if "detail" in c[1].lower()]
            chosen = det[0] if det else (cands[0] if cands else None)
            if chosen:
                used.add(chosen[0])
                return chosen[0]
        return None

    buckets = {
        "by_product_or_service": pick(
            [r"disaggregat", r"products and services", r"revenue by (product|type|category)"]
        ),
        "by_reportable_segment": pick(
            [r"reportable segment", r"information by segment", r"business segment", r"segment information.*detail"]
        ),
        "by_geography": pick(
            [r"countries that individually", r"revenue.*geograph", r"geograph"]
        ),
    }

    got: dict[str, Any] = {}
    for name, rfile in buckets.items():
        if not rfile:
            continue
        html_txt = await _get(client, f"{base}/{rfile}")
        if not html_txt:
            continue
        parsed = parse_details_table(html_txt)
        if parsed:
            got[name] = parsed

    if got:
        result = {
            "available": True,
            "source_filing": f"10-K filed {filing['date']} (acc {filing['accession']})",
            "note": (
                "Reportable segments may be geographic or business lines "
                "depending on the company."
            ),
            **got,
        }
    else:
        result["reason"] = "no segment tables parsed"
    _CACHE[key] = (time.time(), result)
    return result
