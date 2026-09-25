import os, sys, requests, time
from dotenv import load_dotenv
load_dotenv()

token = os.environ.get("WB_TOKEN")
if not token:
    print("WB_TOKEN не найден в .env. Добавьте строку:\nWB_TOKEN=ваш_токен_wb")
    sys.exit(1)

BASE = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"
H = {"Authorization": token}

def page(take=1000, skip=0):
    r = requests.get(
        BASE,
        headers=H,
        params={
            "isAnswered": "false",
            "take": take,
            "skip": skip,
            "order": "dateDesc",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json() or {}

try:
    resp = page(take=1, skip=0)  # быстрый вызов ради шапки с countUnanswered
except requests.HTTPError as e:
    print("HTTP ошибка от WB:", e.response.status_code, e.response.text[:400])
    sys.exit(1)
except requests.RequestException as e:
    print("Сетевая ошибка:", str(e))
    sys.exit(1)

data = resp.get("data") or {}
count_unanswered = data.get("countUnanswered")
print(f"countUnanswered по этому токену: {count_unanswered}")

# Теперь реальный проход по страницам по 1000 шт., чтобы посчитать «сколько реально отдаёт API»
total = 0
skip = 0
take = 1000
while True:
    resp = page(take=take, skip=skip)
    d = resp.get("data") or {}
    arr = d.get("feedbacks") or []
    total += len(arr)
    print(f"Страница skip={skip}: получено {len(arr)}")
    if len(arr) < take:
        break
    skip += len(arr)
    time.sleep(0.35)  # соблюдаем лимиты

print(f"Всего получено через API сейчас: {total}")

# Покажем пример одного отзыва, если есть
if total > 0:
    # Чтобы не делать лишний вызов, используем последний resp/arr
    if not arr:
        # если последняя страница пустая, запросим первую
        resp = page(take=1, skip=0)
        d = resp.get("data") or {}
        arr = d.get("feedbacks") or []
    if arr:
        fb = arr[0]
        print("Пример полей первого отзыва (из последней выборки):")
        for key in ("id","userName","productValuation","createdDate","text"):
            print(f"  {key}: {fb.get(key)}")
