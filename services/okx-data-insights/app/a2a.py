from __future__ import annotations

from typing import Any, Dict

from .models import InsightRequest
from .service import InsightService


def get_manifest() -> Dict[str, Any]:
    return {
        "service_name": "okx-data-insights-asp",
        "display_name": "数据洞察 · Data Insights",
        "version": "1.0.0",
        "description": (
            "分析师带队,把表格和数据库变成看得懂的洞察和图表。一个 ASP,四个助手:"
            "数据分析师(统计画像/相关性/异常/图表建议)、数据库分析师(表数据转 SQLite,"
            "只读 SQL 或自然语言查询)、表格操作员(筛选/排序/分组聚合/派生列)、"
            "快查助手(计数/极值/求和/去重/查找,或实时 OKX 现货报价)。"
        ),
        "mode": "a2a",
        "capabilities": [
            "data_analyst", "database_analyst", "spreadsheet_operator", "quick_query",
        ],
        "input_schema": {
            "type": "object",
            "required": ["assistant"],
            "additionalProperties": True,
            "properties": {
                "assistant": {"type": "string",
                              "enum": ["data_analyst", "database_analyst",
                                       "spreadsheet_operator", "quick_query"]},
                "table": {"description": "{columns,rows} | list of records | {csv:'...'}"},
                "question": {"type": "string"},
                "sql": {"type": "string", "description": "read-only SELECT (database_analyst)"},
                "ops": {"type": "array", "items": {"type": "object"},
                        "description": "pipeline for spreadsheet_operator"},
                "op": {"type": "object", "description": "single op for quick_query"},
            },
            "x-field-naming": "snake_case and camelCase both accepted; unknown keys ignored.",
        },
        "output_schema": {
            "type": "object",
            "required": ["assistant", "markdown"],
            "properties": {
                "assistant": {"type": "string"},
                "markdown": {"type": "string"},
                "charts": {"type": "array", "description": "Vega-Lite specs (data_analyst)"},
            },
        },
        "transport": {
            "protocol": "http",
            "methods": {
                "health": {"method": "GET", "path": "/health"},
                "manifest": {"method": "GET", "path": "/a2a/manifest"},
                "invoke": {"method": "POST", "path": "/a2a/invoke"},
            },
        },
        "pricing": {"amount": "1", "currency": "USDT", "per": "call", "network": "eip155:196"},
        "notes": [
            "Deterministic analysis — no LLM key required; runs on the data you send.",
            "database_analyst executes only read-only SELECT statements in a sandboxed in-memory SQLite.",
            "data_analyst returns Vega-Lite chart specs a buyer agent can render directly.",
            "quick_query can also fetch a live OKX public spot price (no key).",
        ],
    }


class A2AAdapter:
    def __init__(self, service: InsightService) -> None:
        self.service = service

    def manifest(self) -> Dict[str, Any]:
        return get_manifest()

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # unwrap common A2A envelopes
        if isinstance(payload, dict):
            payload = payload.get("input") or payload.get("arguments") or payload.get("params") or payload
        req = InsightRequest.model_validate(payload)
        return self.service.run(req)
