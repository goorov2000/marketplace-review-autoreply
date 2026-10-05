#!/usr/bin/env python3
"""Один запуск на VPS; по умолчанию только предварительный просмотр ответов."""
from __future__ import annotations

import argparse
import base64
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import runpy
import sys
import time

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def validate(env: dict[str, str], market: str, publish: bool) -> list[str]:
    required = ["OPENAI_API_KEY"]
    required += ["WB_TOKEN"] if market == "wb" else ["OZON_CLIENT_ID", "OZON_API_KEY"]
    errors = [f"Не задан {key}" for key in required if not env.get(key, "").strip()]
    for key in ("DRY_RUN", "SKIP_EMPTY", "ONLY_UNANSWERED", "MARK_EMPTY_AS_PROCESSED"):
        if key in env and env[key] not in {"0", "1"}:
            errors.append(f"{key} должен быть 0 или 1")
    for key in ("MAX_COUNT", "MAX_PAGES", "PAGE_LIMIT", "OPENAI_MAXTOKENS"):
        if key in env:
            try:
                if int(env[key]) < 1:
                    raise ValueError()
            except ValueError:
                errors.append(f"{key} должен быть положительным числом")
    token = env.get("WB_TOKEN", "").removeprefix("Bearer ").strip()
    if market == "wb" and token:
        try:
            part = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
            if float(claims["exp"]) <= time.time():
                errors.append("WB_TOKEN истёк — нужен новый токен категории «Вопросы и отзывы»")
            scope = int(claims["s"])
            if not scope & (1 << 7):
                errors.append("WB_TOKEN не содержит категорию «Вопросы и отзывы»")
            if publish and scope & (1 << 30):
                errors.append("WB_TOKEN допускает только чтение")
        except (ValueError, TypeError, KeyError, IndexError):
            errors.append("Не удалось проверить срок и права WB_TOKEN")
    return errors


class RedactSecrets(logging.Filter):
    def __init__(self, env: dict[str, str]):
        super().__init__()
        self.values = [value for key, value in env.items()
                       if ("TOKEN" in key or "API_KEY" in key) and len(value) > 8]

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        for value in self.values:
            text = text.replace(value, "[secret]")
        text = re.sub(r"sk-[A-Za-z0-9_-]+", "[secret]", text)
        text = re.sub(r"eyJ[A-Za-z0-9_.-]+", "[secret]", text)
        record.msg, record.args = text, ()
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("market", choices=("wb", "ozon"))
    parser.add_argument("--env-file", type=Path, default=Path("/srv/jlp/secrets/ai-answers.env"))
    parser.add_argument("--state-dir", type=Path, default=Path("/srv/jlp/data/ai-answers"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true", help="публиковать; нужен <market>.enabled")
    mode.add_argument("--check", action="store_true", help="проверить настройки без сетевых запросов")
    args = parser.parse_args(argv)

    if not args.env_file.is_file() or args.env_file.is_symlink():
        print("Нужен обычный файл секретов --env-file", file=sys.stderr)
        return 2
    if args.env_file.stat().st_mode & 0o007:
        print("Файл секретов доступен посторонним: установите права 640 или 600", file=sys.stderr)
        return 2
    # Только этот файл — исключаем случайные токены из окружения оболочки и .env репо.
    env = {key: value for key, value in dotenv_values(args.env_file, interpolate=False).items()
           if value is not None}
    errors = validate(env, args.market, args.publish)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 2
    if args.check:
        print(f"{args.market}: настройки заполнены; сеть и публикация не проверялись")
        return 0
    if args.publish and not (args.state_dir / f"{args.market}.enabled").is_file():
        print("Публикация не включена: сначала отключите прежнее задание и проверьте сухой прогон", file=sys.stderr)
        return 2

    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o770)
    with (args.state_dir / f"{args.market}.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"{args.market}: предыдущий запуск ещё работает")
            return 0
        # runpy использует этот процесс, поэтому файл остаётся открытым весь прогон.
        for key in ("WB_TOKEN", "OZON_CLIENT_ID", "OZON_API_KEY", "OPENAI_API_KEY",
                    "OPENAI_PROJECT", "OPENAI_MODEL", "DRY_RUN", "MAX_COUNT", "MAX_PAGES",
                    "PAGE_LIMIT", "MARK_EMPTY_AS_PROCESSED", "SKIP_EMPTY", "ONLY_UNANSWERED",
                    "PROMPT_PATH", "CLASSIFICATION_RULES_PATH", "SCENARIOS_PATH",
                    "SYSTEM_PROMPT_PATH", "USER_TEMPLATE_PATH", "OPENAI_MAXTOKENS",
                    "EMPTY_REPLY_LEVEL", "LOG_LEVEL", "LOG_SHOW_LLM", "LOG_PII_MASK",
                    "LOG_MAX_LLM"):
            os.environ.pop(key, None)
        os.environ.update(env)
        os.environ["DRY_RUN"] = "0" if args.publish else "1"
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
        os.environ.setdefault("MAX_COUNT", "20")
        os.environ.setdefault("PAGE_LIMIT", "100")
        os.environ.setdefault("LOG_SHOW_LLM", "0")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        for handler in logging.getLogger().handlers:
            handler.addFilter(RedactSecrets(env))

        directory = ROOT / args.market
        os.chdir(directory)
        sys.path.insert(0, str(directory))
        try:
            runpy.run_path(str(directory / f"{args.market}_reviews_reply.py"), run_name="__main__")
        except SystemExit as result:
            return int(result.code or 0)
        except Exception as error:
            logging.error("Запуск прерван: %s", error)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
