from __future__ import annotations

import json
from typing import List

from .models import Plan


class Presenter:
    def render_json(self, plans: List[Plan]) -> dict:
        return {"plans": [p.model_dump() for p in plans]}

    def render_markdown(self, plans: List[Plan]) -> str:
        lines: List[str] = []
        for i, plan in enumerate(plans, 1):
            lines.append(f"## Option {i}: {plan.title}")
            lines.append(f"- **Score**: {plan.score:.2f}")
            lines.append(f"- **Summary**: {plan.summary}")
            lines.append(f"- **Budget**: {json.dumps(plan.budget_breakdown)}")
            if plan.flight:
                lines.append(
                    f"- **Flight**: {plan.flight.departure} → {plan.flight.arrival}, "
                    f"{plan.flight.duration_minutes} min, ${plan.flight.price_usd} ({plan.flight.provider})"
                )
            if plan.hotel:
                lines.append(
                    f"- **Hotel**: {plan.hotel.name} — ${plan.hotel.price_usd_per_night}/night, "
                    f"rating {plan.hotel.score} ({plan.hotel.address})"
                )
            lines.append("- **Crypto-friendly notes**:")
            for note in plan.crypto_friendly_notes:
                lines.append(f"  - {note}")
            lines.append("- **Daily itinerary**:")
            for d, day in enumerate(plan.pois_by_day, 1):
                names = ", ".join(p.name for p in day) if day else "(no POIs found)"
                lines.append(f"  - Day {d}: {names}")
            lines.append("")
        return "\n".join(lines).strip()
