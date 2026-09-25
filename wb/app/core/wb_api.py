import json
from typing import Any, Dict

import requests


class WBClient:
    def __init__(self, token: str, base: str = "https://feedbacks-api.wildberries.ru/api/v1"):
        self.base = base
        normalized = (token or "").strip()
        if normalized.lower().startswith("bearer "):
            normalized = normalized[7:].strip()
        self.headers = {"Authorization": normalized}

    def list_feedbacks(self, take: int = 100, skip: int = 0) -> Dict[str, Any]:
        params = dict(isAnswered="false", take=take, skip=skip, order="dateDesc")
        r = requests.get(f"{self.base}/feedbacks", headers=self.headers, params=params, timeout=30)
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            if r.status_code == 401:
                raise RuntimeError(
                    "WB вернул 401 Unauthorized: проверьте WB_TOKEN "
                    "(актуальность, права доступа и формат без префикса Bearer)."
                ) from e
            raise
        return (r.json() or {}).get("data") or {}

    def answer(self, feedback_id: str, text: str):
        payload = {"id": feedback_id, "text": text}
        r = requests.post(
            f"{self.base}/feedbacks/answer",
            headers={**self.headers, "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30,
        )
        if r.status_code not in (200, 204):
            raise RuntimeError(f"WB answer failed {r.status_code}: {r.text}")
