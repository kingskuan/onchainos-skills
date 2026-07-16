from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

Assistant = Literal["data_analyst", "database_analyst", "spreadsheet_operator", "quick_query"]


class InsightRequest(BaseModel):
    # Tolerant of snake_case/camelCase + common synonyms so a paid call never
    # 422s on a minor field-name mismatch.
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    assistant: Assistant = Field(
        ..., description="Which of the four assistants to run",
        validation_alias=AliasChoices("assistant", "role", "agent", "mode"))
    table: Any = Field(
        None, description="Tabular data: {columns,rows} | [ {..}, .. ] | {csv:'...'}",
        validation_alias=AliasChoices("table", "data", "dataset", "rows_data"))
    question: Optional[str] = Field(
        None, validation_alias=AliasChoices("question", "q", "ask", "prompt"))
    sql: Optional[str] = Field(None, description="Read-only SELECT for database_analyst")
    ops: List[Dict[str, Any]] = Field(
        default_factory=list, description="Pipeline ops for spreadsheet_operator",
        validation_alias=AliasChoices("ops", "operations", "pipeline"))
    op: Optional[Dict[str, Any]] = Field(
        None, description="Single op for quick_query",
        validation_alias=AliasChoices("op", "quick"))
