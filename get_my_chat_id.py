import sys
import httpx
import re
from pathlib import Path
from config import TELEGRAM_BOT_TOKEN, BASE_DIR

def check_chat_id():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    resp = httpx.get(url).json()
    if not resp.get("ok"):
        print("Ошибка запроса к Telegram API:", resp)
        return None

    results = resp.get("result", [])
    if not results:
        print("Сообщений пока нет. Откройте @sale_penkau_bot и нажмите Start!")
        return None

    last_msg = results[-1]
    chat = last_msg.get("message", {}).get("chat", {}) or last_msg.get("my_chat_member", {}).get("chat", {})
    chat_id = chat.get("id")
    user_name = chat.get("username") or chat.get("first_name", "User")

    if chat_id:
        print(f"УСПЕХ! Найден Chat ID: {chat_id} (Пользователь: {user_name})")
        # Update .env
        env_path = BASE_DIR / ".env"
        env_content = env_path.read_text()
        new_content = re.sub(r"TELEGRAM_CHAT_ID=.*", f"TELEGRAM_CHAT_ID={chat_id}", env_content)
        env_path.write_text(new_content)
        print("Chat ID автоматически сохранен в .env!")

        # Send greeting message
        welcome_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        httpx.post(welcome_url, json={
            "chat_id": chat_id,
            "text": "👋 <b>Привет! Я ваш бот по поиску квартир и суперскидок!</b>\n\nЯ подключен и готов присылать вам горячие находки по Киеву и магазинам.",
            "parse_mode": "HTML"
        })
        return chat_id
    return None

if __name__ == "__main__":
    check_chat_id()
