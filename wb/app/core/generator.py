import json
import logging
import time
from typing import Any

import requests


class OpenAIReplyGenerator:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        project: str = "",
        temperature: float = 0.35,
    ):
        self.url = "https://api.openai.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if project:
            self.headers["OpenAI-Project"] = project
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        for attempt in range(6):
            r = requests.post(self.url, headers=self.headers, data=json.dumps(body), timeout=60)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()

            if r.status_code == 429:
                delay = int(r.headers.get("retry-after", "0")) or (2**attempt)
                logging.warning("[429 OpenAI] waiting %s sec", delay)
                time.sleep(delay)
                continue

            logging.error("[OpenAI] error %s: %s", r.status_code, r.text[:300])
            r.raise_for_status()

        raise RuntimeError("OpenAI generation failed after retries")
