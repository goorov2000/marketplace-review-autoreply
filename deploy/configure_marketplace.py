#!/usr/bin/env python3
"""Скрытый ввод токенов маркетплейса. OpenAI-ключ и остальные строки сохраняются."""
import argparse
import getpass
import grp
import os
from pathlib import Path
import sys
import tempfile

from dotenv import dotenv_values, set_key
import requests

from run import validate


def save(path: Path, values: dict[str, str]) -> None:
    if path.is_symlink():
        raise ValueError("Файл секретов не должен быть симлинком")
    current = path.read_text() if path.exists() else ""
    fd, temporary = tempfile.mkstemp(prefix=".ai-answers-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(current)
        for key, value in values.items():
            set_key(temporary, key, value, quote_mode="always")
        os.chmod(temporary, 0o640)
        os.chown(temporary, -1, grp.getgrnam("jlp").gr_gid)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def probe(market: str, values: dict[str, str]) -> None:
    if market == "wb":
        response = requests.get(
            "https://feedbacks-api.wildberries.ru/api/v1/feedbacks",
            headers={"Authorization": values["WB_TOKEN"]},
            params={"isAnswered": "false", "take": 1, "skip": 0}, timeout=30,
        )
    else:
        response = requests.post(
            "https://api-seller.ozon.ru/v1/review/list",
            headers={"Client-Id": values["OZON_CLIENT_ID"], "Api-Key": values["OZON_API_KEY"]},
            json={"limit": 20, "status": "UNPROCESSED", "sort_dir": "ASC"}, timeout=30,
        )
    if response.status_code != 200:
        # Тело ответа может содержать фрагмент ключа — не выводим его.
        raise ValueError(f"API {market} вернул HTTP {response.status_code}; ключ не сохранён")
    data = response.json()
    if not isinstance(data, dict) or data.get("error") or (market == "ozon" and "reviews" not in data):
        raise ValueError(f"API {market} не подтвердил чтение отзывов; ключ не сохранён")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("market", choices=("wb", "ozon"))
    parser.add_argument("--env-file", type=Path, default=Path("/srv/jlp/secrets/ai-answers.env"))
    args = parser.parse_args()
    if not sys.stdin.isatty():
        print("Запустите в обычном терминале: ввод токенов будет скрыт", file=sys.stderr)
        return 2
    if not args.env_file.is_file() or args.env_file.is_symlink():
        print("Не найден обычный файл секретов с OpenAI-ключом", file=sys.stderr)
        return 2
    env = {k: v for k, v in dotenv_values(args.env_file, interpolate=False).items() if v is not None}
    print("Откройте нужный кабинет продавца. Токен не отображается при вставке.")
    if args.market == "wb":
        print("WB: Интеграции по API → создать токен jlp-ai-answers.")
        print("Категория: только «Вопросы и отзывы». Права: «Чтение и запись».")
        values = {"WB_TOKEN": getpass.getpass("Токен WB: ").strip()}
    else:
        print("Ozon: Настройки → API-ключи. Нужен доступ к отзывам и публикации ответов.")
        values = {"OZON_CLIENT_ID": input("Client ID выбранного кабинета: ").strip(),
                  "OZON_API_KEY": getpass.getpass("Ключ Ozon: ").strip()}
    errors = validate({**env, **values}, args.market, True)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 2
    try:
        probe(args.market, values)
        save(args.env_file, values)
    except (requests.RequestException, ValueError, OSError, KeyError) as error:
        # requests-исключения могут включать URL/ответ; выводим только класс.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(message, file=sys.stderr)
        return 1
    print(f"{args.market}: чтение отзывов проверено, ключ сохранён. Публикация не включалась.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nВвод прерван; ключ не сохранён", file=sys.stderr)
        raise SystemExit(2)
