import json
from pathlib import Path
from typing import Any, Dict


def load_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_user_prompt(template: str, scenario: Dict[str, Any], review: Dict[str, Any], category: str) -> str:
    bables = review.get("bables") or review.get("aspects") or review.get("tags") or []
    return template.format(
        category=category,
        intent=scenario.get("intent", "-"),
        must_include="; ".join(scenario.get("must_include", [])) or "-",
        must_avoid="; ".join(scenario.get("must_avoid", [])) or "-",
        max_sentences=scenario.get("max_sentences", 4),
        user_name=(review.get("userName") or "-").strip() or "-",
        created_date=review.get("createdDate") or review.get("createdTs") or review.get("createdAt") or "-",
        stars=review.get("productValuation") or review.get("valuation") or 0,
        bables=", ".join(map(str, bables)) if bables else "-",
        text=(review.get("text") or "").strip() or "-",
    )
