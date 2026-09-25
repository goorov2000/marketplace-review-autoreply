import os, json, requests
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

api_key = os.environ["OPENAI_API_KEY"]
model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

url = "https://api.openai.com/v1/chat/completions"

# Заголовки запроса
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

# Если есть OPENAI_PROJECT в .env — добавляем
proj = os.getenv("OPENAI_PROJECT")
if proj:
    headers["OpenAI-Project"] = proj

# Тело запроса
body = {
    "model": model,
    "temperature": 0.3,
    "max_tokens": 120,
    "messages": [
        {
            "role": "system",
            "content": "Вы — редактор службы заботы бренда JE LA PECHE. Пишите на русском, вежливо, уважительно и по делу.",
        },
        {
            "role": "user",
            "content": "Сгенерируйте короткую благодарность за отзыв.",
        },
    ],
}

# Отправляем запрос
r = requests.post(url, headers=headers, data=json.dumps(body), timeout=60)
r.raise_for_status()

# Печатаем только ответ модели
print(r.json()["choices"][0]["message"]["content"].strip())
