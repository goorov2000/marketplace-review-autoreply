import os
import json
import time
import logging
import re
import requests

# ===================== НАСТРОЙКИ =====================

OZON_API_BASE   = "https://api-seller.ozon.ru"
CLIENT_ID       = os.getenv("OZON_CLIENT_ID")
API_KEY         = os.getenv("OZON_API_KEY")

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
PROMPT_PATH     = os.getenv("PROMPT_PATH", "prompt_ozon_ru.txt")

DRY_RUN         = os.getenv("DRY_RUN", "1") == "1"
SKIP_EMPTY      = os.getenv("SKIP_EMPTY", "1") == "1"           # пропускать отзывы без текста, если не включён MARK_EMPTY_AS_PROCESSED
ONLY_UNANSWERED = os.getenv("ONLY_UNANSWERED", "1") == "1"

# Новые флаги для «пустых» отзывов
MARK_EMPTY_AS_PROCESSED = os.getenv("MARK_EMPTY_AS_PROCESSED", "0") == "1"  # публиковать заглушку и ставить processed
EMPTY_REPLY_LEVEL       = os.getenv("EMPTY_REPLY_LEVEL", "soft")            # soft | strict

PAGE_LIMIT      = int(os.getenv("PAGE_LIMIT", os.getenv("MAX_COUNT", "100")))   # 20..100
MAX_PAGES       = int(os.getenv("MAX_PAGES", "10"))

LOG_LEVEL       = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_SHOW_LLM    = os.getenv("LOG_SHOW_LLM", "1") == "1"
LOG_PII_MASK    = os.getenv("LOG_PII_MASK", "1") == "1"
LOG_MAX_LLM     = int(os.getenv("LOG_MAX_LLM", "100"))

assert CLIENT_ID and API_KEY, "Нет OZON_CLIENT_ID / OZON_API_KEY"
assert OPENAI_API_KEY, "Нет OPENAI_API_KEY"

HDR = {
    "Client-Id": CLIENT_ID,
    "Api-Key": API_KEY,
    "Content-Type": "application/json"
}

SIGN = "С уважением, команда JE LA PECHE."

# ===================== УТИЛИТЫ =====================

def setup_logging():
    level = logging.DEBUG if LOG_LEVEL == "DEBUG" else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

def api_post(path: str, payload: dict):
    r = requests.post(OZON_API_BASE + path, headers=HDR, data=json.dumps(payload), timeout=30)
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        body = snippet(r.text, 1000)
        raise RuntimeError(f"Ozon API {path} returned {r.status_code}: {body}") from e
    return r.json()

def load_prompt() -> str:
    try:
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return (
            "Вы отвечаете от лица JE LA PECHE на отзывы Ozon. "
            "Структура: приветствие по времени, благодарность, комментарий по сути, "
            "мягкий вопрос при 4★, помощь/сожаление при 1–3★, подпись "
            "'С уважением, команда JE LA PECHE.'; «Вы/Вам/Вас» с заглавной. "
            "Не выводите ничего, кроме финального ответа."
        )

def snippet(s: str, n: int = 220) -> str:
    s = (s or "").strip().replace("\n", " ")
    return (s[:n] + "…") if len(s) > n else s

def mask_pii(s: str) -> str:
    if not LOG_PII_MASK:
        return s or ""
    s = s or ""
    s = re.sub(r'\b[\w\.-]+@[\w\.-]+\.\w+\b', '[email]', s)
    s = re.sub(r'\+?\d[\d\-\s\(\)]{7,}\d', '[phone]', s)
    s = re.sub(r'\b[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+\b', '[name]', s)
    return s

def capitalize_pronouns(text: str) -> str:
    def repl(m):
        w = m.group(0)
        return w[0].upper() + w[1:]
    pattern = r'(?<![А-Яа-яЁёA-Za-z])(вы|вам|вас)(?![А-Яа-яЁёA-Za-z])'
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)

def dedupe_sentences(text: str) -> str:
    t = re.sub(r'[ \t]+', ' ', (text or '')).strip()
    parts = re.split(r'(?<=[\.\!\?])\s+', t)
    seen = set()
    out = []
    for p in parts:
        key = re.sub(r'\s+', ' ', p.strip().lower())
        if key and key not in seen:
            seen.add(key)
            out.append(p.strip())
    s = ' '.join(out)
    s = re.sub(r'(Если потребуется помощь с выбором размера,[^\.]+\.)\s*(?=\1)', r'\1', s, flags=re.IGNORECASE)
    return s

# ===================== REVIEW API =====================

def list_reviews_unprocessed(page_limit: int, max_pages: int):
    page_limit = max(20, min(100, int(page_limit or 100)))
    last_id = None
    prev_last_id = None

    seen_ids = set()
    unique = []

    for _ in range(max_pages):
        payload = {"limit": page_limit, "status": "UNPROCESSED", "sort_dir": "ASC"}
        if last_id:
            payload["last_id"] = last_id

        resp = api_post("/v1/review/list", payload)
        items = resp.get("reviews") or []
        for r in items:
            rid = r.get("id")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                unique.append(r)

        curr_last_id = resp.get("last_id")
        if not items or not resp.get("has_next") or not curr_last_id or curr_last_id == prev_last_id:
            break
        prev_last_id = curr_last_id
        last_id = curr_last_id

    return unique

def list_comments(review_id: str, limit: int = 100, offset: int = 0, sort_dir: str = "ASC"):
    payload = {"review_id": review_id, "limit": max(20, min(100, limit)), "offset": max(0, offset), "sort_dir": sort_dir}
    resp = api_post("/v1/review/comment/list", payload)
    return resp.get("comments") or []

def create_comment(review_id: str, text: str, mark_processed: bool = True, parent_comment_id: str | None = None):
    payload = {"review_id": review_id, "text": text, "mark_review_as_processed": bool(mark_processed)}
    if parent_comment_id:
        payload["parent_comment_id"] = parent_comment_id
    return api_post("/v1/review/comment/create", payload)

# ===================== ЛОГИКА ТЕКСТА =====================

def has_size_issue(text: str) -> bool:
    t = (text or "").lower()
    markers = [
        "не подош",
        "не подходит",
        "не по размер",
        "маломер",
        "большемер",
        "маломерит",
        "большемерит",
        "размер мал",
        "размер больш",
        "размер не",
        "маловат",
        "великоват",
    ]
    if any(m in t for m in markers):
        return True
    if re.search(r'оказал[а-яё]*\s+(больш|мал)', t, flags=re.IGNORECASE):
        return True
    positive = [
        "размер соответствует",
        "соответствует размер",
        "подошёл по размер",
        "подошел по размер",
        "идет в размер",
        "идёт в размер",
        "размер в размер",
    ]
    if any(p in t for p in positive):
        return False
    return False

def has_defect_issue(text: str) -> bool:
    t = (text or "").lower()
    if any(k in t for k in ["затяжк", "дефект", "пятн", "поврежден", "повреждён", "брак", "дыр", "катыш"]):
        return True
    if "нитк" in t and not re.search(r'нитк[а-яё\s]{0,40}(не\s+торч|нигде\s+не\s+торч)', t, flags=re.IGNORECASE):
        return True
    if re.search(r'шв[а-яё\s]{0,40}(крив|разош|торч|неровн|плох)|(крив|разош|торч|неровн|плох)[а-яё\s]{0,40}шв', t, flags=re.IGNORECASE):
        return True
    return False

def has_quality_issue(text: str) -> bool:
    t = (text or "").lower()
    compact = re.sub(r'[^а-яё]+', ' ', t, flags=re.IGNORECASE).strip()
    if compact in ("качество", "качество товара"):
        return True
    if (
        re.search(r'(качество|по качеству)[а-яё\s]{0,30}(плох|ужас|отврат|низк|не\s+оправд|разочар)', t, flags=re.IGNORECASE)
        and not re.search(r'не\s*плох', t, flags=re.IGNORECASE)
    ):
        return True
    return has_defect_issue(t) or any(k in t for k in [
        "скатыва",
        "синтет",
        "цепля",
        "качество не",
        "плохое качество",
        "отвратительный  по качеству",
        "отвратительн",
        "слишком тонк",
        "очень тонк",
        "ткань неприят",
        "жестк",
    ])

def has_packaging_issue(text: str) -> bool:
    t = (text or "").lower()
    if any(k in t for k in ["смят", "помят", "порван", "поврежд"]):
        return True
    return "упаков" in t and any(k in t for k in ["3 бал", "плох", "ужас", "аккурат", "мят"])

def has_wrong_item_issue(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "совсем другое",
        "не тот товар",
        "не та модель",
        "другая модель",
        "модель не соответствует заказанной",
        "вместо",
        "перепутал",
        "коротким рукавом",
    ])

def has_negative_issue(text: str) -> bool:
    t = text or ""
    return (
        has_size_issue(t)
        or has_quality_issue(t)
        or has_packaging_issue(t)
        or has_wrong_item_issue(t)
        or any(k in t.lower() for k in ["запах", "воня", "пахн", "не совпадает", "не соответствует", "не выкуп"])
    )

def classify(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["запах", "воня", "пахн"]): return "запах"
    if has_wrong_item_issue(t): return "ошибка при отгрузке"
    if has_size_issue(t): return "размер"
    if has_packaging_issue(t): return "упаковка"
    if any(k in t for k in ["не совпадает", "не соответствует", "цвет не", "как на фото", "другое фото"]): return "несоответствие фото"
    if has_quality_issue(t): return "качество ткани"
    return "прочее"

def local_template(name: str | None, stars: int | None, text: str) -> str | None:
    if int(stars or 0) >= 5 and not has_negative_issue(text):
        name_part = f"{name}, " if name else ""
        return f"{name_part}благодарим Вас за высокую оценку! Нам очень приятно, что изделие Вам понравилось. Будем рады видеть Вас снова.\n{SIGN}"
    return None

def gen_with_openai(name, stars, text, created_iso=None):
    prompt_text = load_prompt()
    payload_for_llm = {
        "userName": name or "",
        "createdDate": created_iso or __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "text": text or "",
        "bables": classify(text or ""),
        "stars": int(stars or 0)
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": json.dumps(payload_for_llm, ensure_ascii=False)}
        ],
        "temperature": 0.3
    }
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body, timeout=30)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]["content"].strip()

    if not msg.endswith(SIGN):
        msg = (msg + ("\n" if msg.endswith((".", "!")) else ".\n")) + SIGN

    msg = capitalize_pronouns(msg)
    return msg, payload_for_llm

def fix_response(model_reply: str, stars: int, cls: str, raw_text: str) -> str:
    txt = (raw_text or "").lower()
    out = (model_reply or "").strip()

    size_flags = has_size_issue(txt)
    defect_flags = has_defect_issue(txt)

    if (size_flags or defect_flags) and int(stars or 0) >= 5:
        out = re.sub(r'Мы\s+рады,?\s+что\s+Вы\s+оценили[^\.!?]*5★[^\.!?]*[\.!?]?\s*', '', out, flags=re.IGNORECASE)

    if has_quality_issue(txt):
        positive_patterns = [
            r'Мы рады, что Вы остались довольны покупкой,?\s*и\s+надеемся,?\s+что\s+она\s+будет\s+служить\s+Вам\s+долго[\.!?]?\s*',
            r'Мы рады, что Вам понравился наш товар,?\s*и\s+надеемся,?\s+что\s+он\s+будет\s+служить\s+Вам\s+долго[\.!?]?\s*',
            r'Мы рады, что Вы остались довольны покупкой[,\.\!?]?\s*',
            r'Мы рады, что Вам понравился наш товар[,\.\!?]?\s*',
            r'Мы рады, что она будет служить Вам долго[\.!?]?\s*',
            r'Надеемся, что он будет служить Вам долго[\.!?]?\s*',
            r'Надеемся, что она будет служить Вам долго[\.!?]?\s*',
        ]
        for pattern in positive_patterns:
            out = re.sub(pattern, '', out, flags=re.IGNORECASE)
        if not re.search(r'сожале|жаль|не оправдал', out, flags=re.IGNORECASE):
            add = " Сожалеем, что товар не полностью оправдал Ваши ожидания."
            if out.endswith(SIGN):
                out = out[:-len(SIGN)].rstrip()
                out += add + "\n" + SIGN
            else:
                out += add

    if size_flags:
        out = re.sub(
            r'Мы\s+рады,?\s+что\s+Вы\s+обратили\s+внимание\s+на\s+размер[,\.\!?]?\s*',
            'Сожалеем, что размер не подошёл. ',
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(
            r'(Сожалеем, что размер не подошёл\.)\s+и\s+готовы',
            r'\1 Готовы',
            out,
            flags=re.IGNORECASE,
        )
        for bad in [
            "Мы рады, что Вы остались довольны покупкой",
            "Мы рады, что Вы остались довольны",
            "Рады, что Вы остались довольны"
        ]:
            out = out.replace(bad, "Благодарим Вас за отзыв")
        has_help = bool(re.search(
            r'размерн\w*\s+сетк\w*|помо\w*\s+с\s+подбор|помощь\s+с\s+выбором\s+размера',
            out,
            flags=re.IGNORECASE,
        ))
        if not has_help:
            add = " Если потребуется помощь с выбором размера, пожалуйста, напишите в раздел «Вопросы» — подскажем по размерной сетке."
            if out.endswith(SIGN):
                out = out[:-len(SIGN)].rstrip()
                out += add + "\n" + SIGN
            else:
                out += add

    if defect_flags and ("сожале" not in out.lower() and "жаль" not in out.lower()):
        add = " Нам жаль, что Вы столкнулись с этим. Иногда подобное возможно при транспортировке или после предыдущего возврата."
        if out.endswith(SIGN):
            out = out[:-len(SIGN)].rstrip()
            out += add + "\n" + SIGN
        else:
            out += add

    out = re.sub(r'проверим\s+парт(ию|ии)', 'учтём замечание', out, flags=re.IGNORECASE)

    out = capitalize_pronouns(out)
    out = dedupe_sentences(out)

    return out

def empty_review_comment(stars: int, level: str = "soft") -> str:
    if level not in ("soft", "strict"):
        level = "soft"
    if stars >= 4:
        base = "Спасибо за отзыв! Если захотите поделиться подробностями, будем рады в разделе «Вопросы»."
    elif stars == 3:
        base = "Спасибо за отзыв. Если поделитесь подробностями в разделе «Вопросы», мы сможем точнее помочь."
    else:
        base = "Спасибо за отзыв. Сожалеем, что опыт оказался неудачным. Напишите, пожалуйста, детали в разделе «Вопросы», чтобы мы могли помочь."
    if level == "strict":
        base = "Спасибо за отзыв! Если будут детали — напишите, пожалуйста, в «Вопросы»."
    return base

def log_llm(id_: str, stars: int, cls: str, text_in: str, reply_out: str):
    if not LOG_SHOW_LLM:
        return
    safe_in = snippet(mask_pii(text_in or ""), 260)
    safe_out = reply_out if len(reply_out) <= 1200 else reply_out[:1200] + "…"
    logging.info("[LLM] id=%s ★%s cls=%s | in: '%s' | out: %s", id_, stars, cls, safe_in, safe_out)

# ===================== ОСНОВНОЙ ХОД =====================

def main():
    setup_logging()

    reviews = list_reviews_unprocessed(PAGE_LIMIT, MAX_PAGES)

    candidates = []
    failed = 0
    empty_published = 0
    for r in reviews:
        rid = r.get("id")
        stars = int(r.get("rating") or 0)
        text = r.get("text") or ""
        created_iso = r.get("published_at")
        buyer_name = ""

        # Если отзыв без текста:
        if not text.strip():
            # Если включён режим автопометки — публикуем короткую заглушку и переводим в processed
            if MARK_EMPTY_AS_PROCESSED:
                reply = empty_review_comment(stars, level=EMPTY_REPLY_LEVEL)
                try:
                    if DRY_RUN:
                        logging.info("[EMPTY->PROC] id=%s ★%s | out: %s", rid, stars, reply)
                    else:
                        _ = create_comment(rid, reply, mark_processed=True)
                        empty_published += 1
                        time.sleep(0.5)
                except Exception as e:
                    failed += 1
                    logging.warning("Ошибка по пустому отзыву id=%s: %s", rid, e)
                # Уже обработали — дальше не идём
                continue
            # Иначе работаем по старой логике: можно пропустить такие отзывы
            if SKIP_EMPTY:
                continue

        # Если просим только без ответов — проверяем
        if ONLY_UNANSWERED:
            if (r.get("comments_amount") or 0) > 0:
                comments = list_comments(rid, limit=20, offset=0, sort_dir="ASC")
                if comments:
                    continue

        candidates.append({"id": rid, "stars": stars, "text": text, "created": created_iso, "name": buyer_name})

    processed_llm = processed_local = published = 0
    llm_logs_emitted = 0

    for c in candidates:
        try:
            cls = classify(c["text"])
            reply = local_template(c["name"], c["stars"], c["text"])
            used_llm = False

            if reply is None:
                used_llm = True
                reply, _ = gen_with_openai(c["name"], c["stars"], c["text"], c["created"])
                reply = fix_response(reply, c["stars"], cls, c["text"])

            if DRY_RUN:
                pass
            else:
                _ = create_comment(c["id"], reply, mark_processed=True)
                published += 1
                time.sleep(0.6)

            if used_llm and llm_logs_emitted < LOG_MAX_LLM:
                log_llm(c["id"], c["stars"], cls, c["text"], reply)
                llm_logs_emitted += 1

            if used_llm:
                processed_llm += 1
            else:
                processed_local += 1

        except Exception as e:
            failed += 1
            logging.warning("Ошибка по id=%s: %s", c.get("id"), e)

    logging.info("Готово. Ответов: LLM=%d, local=%d, опубликовано=%d, пустых опубликовано=%d, ошибок=%d (DRY_RUN=%s)",
                 processed_llm, processed_local, published, empty_published, failed, "1" if DRY_RUN else "0")

if __name__ == "__main__":
    main()
