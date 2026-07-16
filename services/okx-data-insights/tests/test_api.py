from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TABLE = {
    "columns": ["region", "month", "sales", "cost"],
    "rows": [
        ["East", "2026-01", 120, 80],
        ["East", "2026-02", 150, 90],
        ["West", "2026-01", 200, 130],
        ["West", "2026-02", 90, 70],
        ["North", "2026-01", 500, 300],
    ],
}


def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_manifest_lists_four_assistants():
    m = client.get("/a2a/manifest").json()
    assert m["service_name"] == "okx-data-insights-asp"
    assert set(m["capabilities"]) == {
        "data_analyst", "database_analyst", "spreadsheet_operator", "quick_query"}
    assert m["pricing"]["amount"] == "1"


def test_data_analyst():
    r = client.post("/insights", json={"assistant": "data_analyst", "table": TABLE})
    assert r.status_code == 200
    d = r.json()
    assert d["assistant"] == "data_analyst"
    assert d["rows"] == 5
    assert d["column_types"]["sales"] == "number"
    assert d["charts"]                      # at least one chart spec
    assert "## 数据分析师" in d["markdown"]


def test_database_analyst_sql():
    r = client.post("/insights", json={
        "assistant": "database_analyst",
        "table": TABLE,
        "sql": 'SELECT region, SUM(sales) AS s FROM data GROUP BY region ORDER BY s DESC'})
    d = r.json()
    assert d["error"] is None
    assert d["result_columns"][0] == "region"
    assert d["result_rows"][0][0] == "North"       # 500 highest


def test_database_analyst_blocks_writes():
    r = client.post("/insights", json={
        "assistant": "database_analyst", "table": TABLE, "sql": "DROP TABLE data"})
    assert r.json()["error"] is not None


def test_database_analyst_nl():
    r = client.post("/insights", json={
        "assistant": "database_analyst", "table": TABLE,
        "question": "average sales by region"})
    d = r.json()
    assert d["generated_sql"] and "AVG" in d["generated_sql"].upper()


def test_spreadsheet_operator_pipeline():
    r = client.post("/insights", json={
        "assistant": "spreadsheet_operator", "table": TABLE,
        "ops": [
            {"op": "derive", "column": "profit", "expr": "sales - cost"},
            {"op": "filter", "column": "profit", "cmp": ">", "value": 30},
            {"op": "sort", "column": "profit", "desc": True},
            {"op": "limit", "n": 3},
        ]})
    d = r.json()
    assert "profit" in d["columns"]
    assert d["rows"][0]["profit"] == 200           # North: 500-300
    assert d["row_count"] <= 3


def test_quick_query_agg():
    r = client.post("/insights", json={
        "assistant": "quick_query", "table": TABLE, "op": {"op": "max", "column": "sales"}})
    assert r.json()["answer"] == 500


def test_camelcase_and_mcp():
    # camelCase alias + MCP dispatch
    r = client.post("/mcp", json={"tool": "quick_query",
                                  "arguments": {"data": TABLE, "op": {"op": "count"}}})
    assert r.status_code == 200
    assert r.json()["answer"] == 5


def test_a2a_invoke_envelope():
    r = client.post("/a2a/invoke", json={"input": {"assistant": "data_analyst", "table": TABLE}})
    assert r.status_code == 200
    assert r.json()["assistant"] == "data_analyst"
