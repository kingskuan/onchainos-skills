"""The four Data-Insights assistants (deterministic, stdlib only).

  data_analyst        — profile a table: stats, correlations, outliers, trend,
                        narrative findings + chart specs (Vega-Lite).
  database_analyst    — load the table into in-memory SQLite; run a read-only SQL
                        query, or translate a simple natural-language question.
  spreadsheet_operator— apply a pipeline of table ops (filter/sort/select/
                        groupby/derive/limit).
  quick_query         — one fast answer (count/max/min/sum/mean/lookup/distinct),
                        or a live OKX spot price for "price of BTC" style asks.
"""
from __future__ import annotations

import ast
import json
import math
import re
import sqlite3
import statistics as st
import urllib.request
from typing import Any, Dict, List, Optional

from . import tableutil as T


# ----------------------------- shared stats -----------------------------------
def _describe(nums: List[float]) -> Dict[str, Any]:
    if not nums:
        return {"count": 0}
    s = sorted(nums)
    n = len(s)
    q = lambda p: s[min(n - 1, max(0, int(round(p * (n - 1)))))]
    return {
        "count": n,
        "mean": round(st.fmean(s), 6),
        "median": round(st.median(s), 6),
        "min": s[0],
        "max": s[-1],
        "std": round(st.pstdev(s), 6) if n > 1 else 0.0,
        "p25": q(0.25),
        "p75": q(0.75),
    }


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs2, ys2 = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = st.fmean(xs2), st.fmean(ys2)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs2))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys2))
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 4)


# ----------------------------- 1) data analyst --------------------------------
def data_analyst(table: Any) -> Dict[str, Any]:
    cols, records = T.normalize(table)
    types = T.infer_types(cols, records)
    num_cols = T.numeric_columns(cols, types)
    cat_cols = T.categorical_columns(cols, types)

    profile = {c: (_describe(T.col_numbers(records, c)) if types[c] == "number"
                   else {"type": types[c], "unique": len({str(r.get(c)) for r in records})})
               for c in cols}

    # correlations between numeric pairs
    correlations = []
    for i in range(len(num_cols)):
        for j in range(i + 1, len(num_cols)):
            a, b = num_cols[i], num_cols[j]
            r = _pearson(T.col_numbers(records, a), T.col_numbers(records, b))
            if r is not None:
                correlations.append({"a": a, "b": b, "r": r})
    correlations.sort(key=lambda x: abs(x["r"]), reverse=True)

    # outliers via IQR per numeric column
    outliers = {}
    for c in num_cols:
        nums = T.col_numbers(records, c)
        d = _describe(nums)
        if d["count"] >= 4:
            iqr = d["p75"] - d["p25"]
            lo, hi = d["p25"] - 1.5 * iqr, d["p75"] + 1.5 * iqr
            hits = [x for x in nums if x < lo or x > hi]
            if hits:
                outliers[c] = {"low_bound": round(lo, 4), "high_bound": round(hi, 4),
                               "count": len(hits), "examples": hits[:5]}

    # category distributions
    distributions = {}
    for c in cat_cols:
        counts: Dict[str, int] = {}
        for r in records:
            k = str(r.get(c))
            counts[k] = counts.get(k, 0) + 1
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
        distributions[c] = [{"value": k, "count": v} for k, v in top]

    # narrative findings
    findings: List[str] = [f"Dataset has {len(records)} rows and {len(cols)} columns "
                           f"({len(num_cols)} numeric, {len(cat_cols)} categorical)."]
    for c in num_cols[:4]:
        d = profile[c]
        findings.append(f"'{c}': mean {d['mean']}, median {d['median']}, "
                        f"range [{d['min']}, {d['max']}].")
    if correlations:
        top = correlations[0]
        strength = "strong" if abs(top["r"]) >= 0.7 else "moderate" if abs(top["r"]) >= 0.4 else "weak"
        direction = "positive" if top["r"] > 0 else "negative"
        findings.append(f"Strongest relationship: '{top['a']}' vs '{top['b']}' "
                        f"({strength} {direction}, r={top['r']}).")
    for c, o in list(outliers.items())[:2]:
        findings.append(f"'{c}' has {o['count']} outlier(s) outside [{o['low_bound']}, {o['high_bound']}].")

    charts = _suggest_charts(cols, types, records, correlations)

    md = _md_report("数据分析师 · Data Analyst", findings,
                    extra={"numeric_profile": {c: profile[c] for c in num_cols}})
    return {
        "assistant": "data_analyst",
        "rows": len(records), "columns": cols, "column_types": types,
        "profile": profile, "correlations": correlations[:10],
        "outliers": outliers, "distributions": distributions,
        "findings": findings, "charts": charts, "markdown": md,
    }


def _suggest_charts(cols, types, records, correlations) -> List[Dict[str, Any]]:
    """Compact Vega-Lite specs a buyer agent can render directly."""
    charts = []
    num_cols = T.numeric_columns(cols, types)
    cat_cols = T.categorical_columns(cols, types)
    time_cols = [c for c in cols if types.get(c) == "datetime"]
    values = records[:500]
    if time_cols and num_cols:
        charts.append({"title": f"{num_cols[0]} over {time_cols[0]}",
                       "vega_lite": {"mark": "line",
                                     "encoding": {"x": {"field": time_cols[0], "type": "temporal"},
                                                  "y": {"field": num_cols[0], "type": "quantitative"}},
                                     "data": {"values": values}}})
    if cat_cols and num_cols:
        charts.append({"title": f"{num_cols[0]} by {cat_cols[0]}",
                       "vega_lite": {"mark": "bar",
                                     "encoding": {"x": {"field": cat_cols[0], "type": "nominal"},
                                                  "y": {"field": num_cols[0], "type": "quantitative",
                                                        "aggregate": "sum"}},
                                     "data": {"values": values}}})
    if correlations:
        top = correlations[0]
        charts.append({"title": f"{top['a']} vs {top['b']} (r={top['r']})",
                       "vega_lite": {"mark": "point",
                                     "encoding": {"x": {"field": top["a"], "type": "quantitative"},
                                                  "y": {"field": top["b"], "type": "quantitative"}},
                                     "data": {"values": values}}})
    if num_cols and not charts:
        charts.append({"title": f"Distribution of {num_cols[0]}",
                       "vega_lite": {"mark": "bar",
                                     "encoding": {"x": {"field": num_cols[0], "bin": True, "type": "quantitative"},
                                                  "y": {"aggregate": "count", "type": "quantitative"}},
                                     "data": {"values": values}}})
    return charts


# --------------------------- 2) database analyst ------------------------------
_SAFE_SQL = re.compile(r"^\s*select\b", re.I)
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace)\b", re.I)


def _load_sqlite(cols, records):
    conn = sqlite3.connect(":memory:")
    safe = [re.sub(r"[^0-9a-zA-Z_]", "_", c) or ("col%d" % i) for i, c in enumerate(cols)]
    col_defs = ", ".join('"%s"' % s for s in safe)
    placeholders = ", ".join("?" for _ in safe)
    conn.execute("CREATE TABLE data (%s)" % col_defs)
    conn.executemany(
        "INSERT INTO data VALUES (%s)" % placeholders,
        [[r.get(c) for c in cols] for r in records],
    )
    conn.commit()
    return conn, dict(zip(safe, cols))


def _nl_to_sql(question: str, cols: List[str], types: Dict[str, str]) -> Optional[str]:
    q = question.lower()
    num = T.numeric_columns(cols, types)
    cat = T.categorical_columns(cols, types)

    def find(names):
        for c in cols:
            if c.lower() in q:
                return c
        return names[0] if names else None

    if re.search(r"\b(count|how many|number of rows)\b", q):
        by = next((c for c in cat if c.lower() in q), None)
        return (f'SELECT "{by}", COUNT(*) AS n FROM data GROUP BY "{by}" ORDER BY n DESC'
                if by else "SELECT COUNT(*) AS row_count FROM data")
    m = re.search(r"\b(average|avg|mean)\b", q)
    if m and num:
        col = find(num)
        by = next((c for c in cat if c.lower() in q), None)
        return (f'SELECT "{by}", AVG("{col}") AS avg_{col} FROM data GROUP BY "{by}" ORDER BY avg_{col} DESC'
                if by else f'SELECT AVG("{col}") AS avg_{col} FROM data')
    if re.search(r"\b(sum|total)\b", q) and num:
        col = find(num)
        by = next((c for c in cat if c.lower() in q), None)
        return (f'SELECT "{by}", SUM("{col}") AS sum_{col} FROM data GROUP BY "{by}" ORDER BY sum_{col} DESC'
                if by else f'SELECT SUM("{col}") AS sum_{col} FROM data')
    tm = re.search(r"top\s+(\d+)", q)
    if tm and num:
        col = find(num)
        return f'SELECT * FROM data ORDER BY "{col}" DESC LIMIT {int(tm.group(1))}'
    if re.search(r"\b(max|highest|largest)\b", q) and num:
        col = find(num)
        return f'SELECT * FROM data ORDER BY "{col}" DESC LIMIT 1'
    if re.search(r"\b(min|lowest|smallest)\b", q) and num:
        col = find(num)
        return f'SELECT * FROM data ORDER BY "{col}" ASC LIMIT 1'
    return None


def database_analyst(table: Any, sql: Optional[str] = None,
                     question: Optional[str] = None) -> Dict[str, Any]:
    cols, records = T.normalize(table)
    types = T.infer_types(cols, records)
    schema = [{"column": c, "type": types[c]} for c in cols]

    generated_sql, note = sql, None
    if not generated_sql and question:
        generated_sql = _nl_to_sql(question, cols, types)
        if not generated_sql:
            note = ("Could not translate the question to SQL automatically; "
                    "returning schema + sample. Provide `sql` for an exact query.")

    result_cols, result_rows, err = [], [], None
    if generated_sql:
        if not _SAFE_SQL.match(generated_sql) or _FORBIDDEN.search(generated_sql):
            err = "Only read-only single SELECT statements are allowed."
        else:
            conn, colmap = _load_sqlite(cols, records)
            try:
                cur = conn.execute(generated_sql.replace(";", ""))
                result_cols = [d[0] for d in cur.description] if cur.description else []
                result_rows = [list(r) for r in cur.fetchall()[:500]]
            except sqlite3.Error as e:
                err = f"SQL error: {e}"
            finally:
                conn.close()

    md = _md_report("数据库分析师 · Database Analyst",
                    [f"Table `data`: {len(records)} rows, {len(cols)} columns.",
                     f"SQL: {generated_sql}" if generated_sql else "No query run — schema returned.",
                     f"Returned {len(result_rows)} row(s)." if generated_sql and not err else (err or note or "")])
    return {
        "assistant": "database_analyst",
        "schema": schema, "row_count": len(records),
        "generated_sql": generated_sql, "result_columns": result_cols,
        "result_rows": result_rows, "error": err, "note": note,
        "sample": records[:5], "markdown": md,
    }


# ------------------------- 3) spreadsheet operator ----------------------------
_ALLOWED_AST = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
                ast.Name, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.Mod, ast.Pow)


def _safe_eval(expr: str, row: Dict[str, Any]) -> Any:
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST):
            raise ValueError(f"unsupported expression element: {type(node).__name__}")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Num):  # py<3.8
            return n.n
        if isinstance(n, ast.Name):
            return T._to_number(row.get(n.id)) or 0.0
        if isinstance(n, ast.UnaryOp):
            return -ev(n.operand)
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            t = type(n.op)
            if t is ast.Add:
                return a + b
            if t is ast.Sub:
                return a - b
            if t is ast.Mult:
                return a * b
            if t is ast.Div:
                return a / b if b else None
            if t is ast.Mod:
                return a % b if b else None
            if t is ast.Pow:
                if abs(a) > 1e6 or abs(b) > 12:      # guard against overflow
                    raise ValueError("exponent too large")
                return a ** b
            raise ValueError("unsupported operator")
        raise ValueError("bad expr")
    return ev(tree)


def spreadsheet_operator(table: Any, ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    cols, records = T.normalize(table)
    steps: List[str] = []
    rows = list(records)

    for op in (ops or []):
        kind = op.get("op")
        if kind == "filter":
            c, cmp, val = op["column"], op.get("cmp", "=="), op.get("value")
            def keep(r, c=c, cmp=cmp, val=val):
                x = r.get(c)
                xn, vn = T._to_number(x), T._to_number(val)
                if cmp in (">", ">=", "<", "<=") and xn is not None and vn is not None:
                    return {">": xn > vn, ">=": xn >= vn, "<": xn < vn, "<=": xn <= vn}[cmp]
                if cmp == "contains":
                    return str(val) in str(x)
                return {"==": str(x) == str(val), "!=": str(x) != str(val)}.get(cmp, False)
            rows = [r for r in rows if keep(r)]
            steps.append(f"filter {c} {cmp} {val} -> {len(rows)} rows")
        elif kind == "sort":
            c = op["column"]
            rows.sort(key=lambda r: (T._to_number(r.get(c)) is None, T._to_number(r.get(c))
                                     if T._to_number(r.get(c)) is not None else str(r.get(c))),
                      reverse=bool(op.get("desc")))
            steps.append(f"sort {c} {'desc' if op.get('desc') else 'asc'}")
        elif kind == "select":
            keep_cols = op["columns"]
            rows = [{k: r.get(k) for k in keep_cols} for r in rows]
            cols = list(keep_cols)
            steps.append(f"select {keep_cols}")
        elif kind == "derive":
            name, expr = op["column"], op["expr"]
            for r in rows:
                try:
                    r[name] = round(_safe_eval(expr, r), 6)
                except Exception:
                    r[name] = None
            if name not in cols:
                cols.append(name)
            steps.append(f"derive {name} = {expr}")
        elif kind == "groupby":
            by = op["by"] if isinstance(op["by"], list) else [op["by"]]
            aggs = op.get("agg", {})
            groups: Dict[tuple, List[Dict]] = {}
            for r in rows:
                groups.setdefault(tuple(str(r.get(b)) for b in by), []).append(r)
            newrows = []
            for key, grp in groups.items():
                nr = dict(zip(by, key))
                for col, fn in aggs.items():
                    nums = [T._to_number(g.get(col)) for g in grp]
                    nums = [x for x in nums if x is not None]
                    nr[f"{fn}_{col}"] = {
                        "sum": sum(nums), "mean": round(st.fmean(nums), 6) if nums else None,
                        "min": min(nums) if nums else None, "max": max(nums) if nums else None,
                        "count": len(grp),
                    }.get(fn)
                newrows.append(nr)
            rows = newrows
            cols = by + [f"{fn}_{col}" for col, fn in aggs.items()]
            steps.append(f"groupby {by} agg {aggs} -> {len(rows)} groups")
        elif kind == "limit":
            rows = rows[: int(op.get("n", 50))]
            steps.append(f"limit {op.get('n', 50)}")

    md = _md_report("表格操作员 · Spreadsheet Operator",
                    steps + [f"Result: {len(rows)} rows × {len(cols)} columns."])
    return {"assistant": "spreadsheet_operator", "steps": steps, "columns": cols,
            "row_count": len(rows), "rows": rows[:500], "markdown": md}


# ----------------------------- 4) quick query ---------------------------------
def _okx_price(symbol: str) -> Optional[Dict[str, Any]]:
    inst = f"{symbol.upper()}-USDT"
    try:
        req = urllib.request.Request(f"https://www.okx.com/api/v5/market/ticker?instId={inst}",
                                     headers={"User-Agent": "okx-data-insights/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode())
        row = (d.get("data") or [None])[0]
        if not row:
            return None
        return {"symbol": symbol.upper(), "inst_id": inst, "last": float(row["last"]),
                "high_24h": float(row["high24h"]), "low_24h": float(row["low24h"])}
    except Exception:
        return None


def quick_query(table: Any = None, op: Optional[Dict[str, Any]] = None,
                question: Optional[str] = None) -> Dict[str, Any]:
    # live OKX price lookup ("price of BTC")
    if question:
        m = re.search(r"price of ([A-Za-z0-9]{2,10})", question, re.I) or \
            re.search(r"([A-Za-z0-9]{2,10})\s+price", question, re.I)
        if m:
            p = _okx_price(m.group(1))
            if p:
                return {"assistant": "quick_query", "kind": "market_price", "answer": p,
                        "markdown": f"**{p['symbol']}** last {p['last']} USDT "
                                    f"(24h {p['low_24h']}–{p['high_24h']})."}

    if table is None:
        return {"assistant": "quick_query", "error": "provide a table + op, or a market price question"}

    cols, records = T.normalize(table)
    op = op or {}
    # infer op from question if not given
    if not op.get("op") and question:
        ql = question.lower()
        for k in ("count", "max", "min", "sum", "mean", "average", "distinct"):
            if k in ql:
                op = {"op": "mean" if k == "average" else k}
                op["column"] = next((c for c in cols if c.lower() in ql), None)
                break

    kind = op.get("op", "count")
    col = op.get("column")
    if kind == "count":
        ans: Any = len(records)
    elif kind == "distinct" and col:
        ans = sorted({str(r.get(col)) for r in records})
    elif kind in ("max", "min", "sum", "mean", "median") and col:
        nums = T.col_numbers(records, col)
        ans = {"max": max(nums) if nums else None, "min": min(nums) if nums else None,
               "sum": sum(nums), "mean": round(st.fmean(nums), 6) if nums else None,
               "median": round(st.median(nums), 6) if nums else None}[kind]
    elif kind == "lookup":
        where = op.get("where", {})
        hits = [r for r in records if all(str(r.get(k)) == str(v) for k, v in where.items())]
        sel = op.get("select")
        ans = [{k: r.get(k) for k in ([sel] if isinstance(sel, str) else sel)} if sel else r
               for r in hits[:50]]
    else:
        ans = {"error": f"unsupported quick op: {kind}"}

    md = _md_report("快查助手 · Quick Query", [f"{kind}"
                    + (f" of '{col}'" if col else "") + f": {ans if not isinstance(ans, list) else str(len(ans))+' result(s)'}"])
    return {"assistant": "quick_query", "kind": kind, "column": col, "answer": ans, "markdown": md}


# ------------------------------- markdown -------------------------------------
def _md_report(title: str, lines: List[str], extra: Optional[Dict[str, Any]] = None) -> str:
    out = [f"## {title}", ""]
    out += [f"- {ln}" for ln in lines if ln]
    if extra:
        out += ["", "```json", json.dumps(extra, ensure_ascii=False, indent=2)[:1500], "```"]
    return "\n".join(out)
