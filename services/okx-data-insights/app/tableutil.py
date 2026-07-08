"""Table normalization + lightweight type inference (stdlib only).

Accepts a table as any of:
  - {"columns": [...], "rows": [[...], ...]}
  - [{"col": val, ...}, ...]                (list of record dicts)
  - {"csv": "a,b\n1,2\n3,4"}                (CSV text)
and returns a normalized (columns, records, coltypes) triple.
"""
from __future__ import annotations

import csv
import io
import math
from datetime import datetime
from typing import Any, Dict, List, Tuple

Records = List[Dict[str, Any]]


def _to_number(v: Any):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s == "":
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


_DATE_FMTS = ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m")


def _is_datetime(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    for f in _DATE_FMTS:
        try:
            datetime.strptime(v.strip(), f)
            return True
        except ValueError:
            continue
    return False


def normalize(table: Any) -> Tuple[List[str], Records]:
    """Return (columns, records) from any accepted table shape."""
    if table is None:
        raise ValueError("no table provided")

    # CSV text
    if isinstance(table, dict) and "csv" in table:
        reader = csv.DictReader(io.StringIO(table["csv"]))
        records = [dict(r) for r in reader]
        cols = list(reader.fieldnames or [])
        return cols, records

    # columns + rows
    if isinstance(table, dict) and "columns" in table and "rows" in table:
        cols = [str(c) for c in table["columns"]]
        records = [dict(zip(cols, row)) for row in table["rows"]]
        return cols, records

    # list of record dicts
    if isinstance(table, list):
        cols: List[str] = []
        for r in table:
            if isinstance(r, dict):
                for k in r.keys():
                    if k not in cols:
                        cols.append(str(k))
        records = [{str(k): v for k, v in r.items()} for r in table if isinstance(r, dict)]
        return cols, records

    # single record dict (already columns/rows handled above)
    if isinstance(table, dict):
        cols = [str(k) for k in table.keys()]
        return cols, [dict(table)]

    raise ValueError("unrecognized table format")


def infer_types(columns: List[str], records: Records) -> Dict[str, str]:
    """Classify each column as number / datetime / bool / string."""
    types: Dict[str, str] = {}
    for c in columns:
        vals = [r.get(c) for r in records if r.get(c) not in (None, "")]
        if not vals:
            types[c] = "string"
            continue
        if all(isinstance(v, bool) for v in vals):
            types[c] = "bool"
        elif all(_to_number(v) is not None for v in vals):
            types[c] = "number"
        elif all(_is_datetime(v) for v in vals):
            types[c] = "datetime"
        else:
            types[c] = "string"
    return types


def col_numbers(records: Records, col: str) -> List[float]:
    out = []
    for r in records:
        n = _to_number(r.get(col))
        if n is not None:
            out.append(n)
    return out


def numeric_columns(columns: List[str], types: Dict[str, str]) -> List[str]:
    return [c for c in columns if types.get(c) == "number"]


def categorical_columns(columns: List[str], types: Dict[str, str]) -> List[str]:
    return [c for c in columns if types.get(c) in ("string", "bool")]
