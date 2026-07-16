from __future__ import annotations

from typing import Any, Dict

from . import analysts
from .models import InsightRequest


class InsightService:
    """Analyst-led dispatch to the four Data-Insights assistants."""

    def run(self, req: InsightRequest) -> Dict[str, Any]:
        a = req.assistant
        if a == "data_analyst":
            return analysts.data_analyst(req.table)
        if a == "database_analyst":
            return analysts.database_analyst(req.table, sql=req.sql, question=req.question)
        if a == "spreadsheet_operator":
            return analysts.spreadsheet_operator(req.table, req.ops)
        if a == "quick_query":
            return analysts.quick_query(req.table, op=req.op, question=req.question)
        raise ValueError(f"unknown assistant: {a}")
