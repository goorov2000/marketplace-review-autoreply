import logging
import os
import time

from dotenv import load_dotenv

from app.core.classifier import ReviewClassifier
from app.core.generator import OpenAIReplyGenerator
from app.core.pipeline import ReplyPipeline
from app.core.wb_api import WBClient

load_dotenv()

WB_TOKEN = os.environ["WB_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_PROJECT = os.getenv("OPENAI_PROJECT", "")
OPENAI_MAXTOKENS = int(os.getenv("OPENAI_MAXTOKENS", "220"))
_dry_run = os.getenv("DRY_RUN", "1")
if _dry_run not in {"0", "1"}:
    raise ValueError("DRY_RUN должен быть 0 или 1")
DRY_RUN = _dry_run == "1"
MAX_COUNT = int(os.getenv("MAX_COUNT", "50"))
if MAX_COUNT < 1:
    raise ValueError("MAX_COUNT должен быть положительным")

RULES_PATH = os.getenv("CLASSIFICATION_RULES_PATH", "app/config/classification_rules.json")
SCENARIOS_PATH = os.getenv("SCENARIOS_PATH", "app/config/scenarios.json")
SYSTEM_PROMPT_PATH = os.getenv("SYSTEM_PROMPT_PATH", "app/prompts/system_ru.txt")
USER_TEMPLATE_PATH = os.getenv("USER_TEMPLATE_PATH", "app/prompts/user_template.txt")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def build_pipeline() -> ReplyPipeline:
    classifier = ReviewClassifier(RULES_PATH)
    generator = OpenAIReplyGenerator(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        max_tokens=OPENAI_MAXTOKENS,
        project=OPENAI_PROJECT,
    )
    return ReplyPipeline(
        classifier=classifier,
        generator=generator,
        scenarios_path=SCENARIOS_PATH,
        system_prompt_path=SYSTEM_PROMPT_PATH,
        user_template_path=USER_TEMPLATE_PATH,
    )


def main():
    logging.info(
        "Старт. DRY_RUN=%s MAX_COUNT=%s MODEL=%s",
        int(DRY_RUN),
        MAX_COUNT,
        OPENAI_MODEL,
    )

    wb = WBClient(WB_TOKEN)
    pipeline = build_pipeline()

    total = 0
    published = 0
    skipped_low_rating = 0
    failed = 0
    skip = 0
    take = 100

    # Сначала снимок кандидатов: публикация удаляет отзыв из isAnswered=false,
    # поэтому смещение по этой выборке нельзя увеличивать во время публикации.
    candidates = []
    # Низкие оценки остаются без ответа: фиксированное окно страниц навсегда
    # скрывало бы старые 4–5★ за ними. Читаем до кандидатов или конца очереди.
    while True:
        data = wb.list_feedbacks(take=take, skip=skip)
        feedbacks = data.get("feedbacks") or []
        count_unanswered = data.get("countUnanswered")

        logging.info(
            "WB: неотвеченных отзывов=%s, получено в пачке=%s (skip=%s, take=%s)",
            count_unanswered,
            len(feedbacks),
            skip,
            take,
        )

        if not feedbacks:
            logging.info("Нет отзывов для обработки.")
            break

        for fb in feedbacks:
            stars = int(fb.get("productValuation") or 0)
            if stars < 4:
                skipped_low_rating += 1
                continue
            candidates.append(fb)
            if len(candidates) >= MAX_COUNT:
                break

        if len(candidates) >= MAX_COUNT or len(feedbacks) < take:
            break

        skip += len(feedbacks)
        time.sleep(0.35)

    # Лимит относится к попыткам, включая неудачные запросы.
    for fb in candidates:
        fid = fb.get("id") or fb.get("feedbackId")
        stars = int(fb.get("productValuation") or 0)
        try:
            artifacts = pipeline.process(fb)
            if DRY_RUN:
                print("\n--- DRY_RUN ---")
                print(f"id: {fid} | stars: {stars} | category: {artifacts.category.value}")
                print(f"reasons: {', '.join(artifacts.reasons)}")
                print(artifacts.final_reply)
                print("---------------")
            else:
                wb.answer(str(fid), artifacts.final_reply)
                published += 1
                logging.info("Ответ опубликован для id=%s", fid)
                time.sleep(0.35)
            total += 1
        except Exception as e:
            logging.error("Ошибка по id=%s: %s", fid, e)
            failed += 1

    logging.info(
        "Готово. Обработано=%s, опубликовано=%s, пропущено(рейтинг<4)=%s, ошибок=%s",
        total,
        published,
        skipped_low_rating,
        failed,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
