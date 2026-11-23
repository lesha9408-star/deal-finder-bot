import time
import logging
import httpx
from config import TELEGRAM_BOT_TOKEN
from database import save_feedback

logger = logging.getLogger(__name__)

def handle_updates():
    offset = 0
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    answer_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    edit_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup"

    while True:
        try:
            params = {"offset": offset, "timeout": 20}
            resp = httpx.get(url, params=params, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    if "callback_query" in update:
                        cb = update["callback_query"]
                        cb_id = cb["id"]
                        cb_data = cb.get("data", "")
                        msg = cb.get("message", {})
                        chat_id = msg.get("chat", {}).get("id")
                        msg_id = msg.get("message_id")
                        msg_text = msg.get("caption") or msg.get("text", "")

                        if "|" in cb_data:
                            action, item_key = cb_data.split("|", 1)
                            if action == "like":
                                save_feedback(item_key, msg_text[:100], "like")
                                httpx.post(answer_url, json={
                                    "callback_query_id": cb_id,
                                    "text": "👍 Рад, что понравилось! Ищу еще больше такого.",
                                    "show_alert": False
                                })
                                new_markup = {"inline_keyboard": [[{"text": "✅ Вам понравилось 👍", "callback_data": "done"}]]}
                            else:
                                save_feedback(item_key, msg_text[:100], "dislike")
                                httpx.post(answer_url, json={
                                    "callback_query_id": cb_id,
                                    "text": "👎 Запомнил! Больше подобное рекомендовать не буду.",
                                    "show_alert": True
                                })
                                new_markup = {"inline_keyboard": [[{"text": "❌ Скрыто из рекомендаций 👎", "callback_data": "done"}]]}

                            httpx.post(edit_url, json={
                                "chat_id": chat_id,
                                "message_id": msg_id,
                                "reply_markup": new_markup
                            })
        except Exception as e:
            logger.error(f"Error handling feedback updates: {e}")
            time.sleep(3)

if __name__ == "__main__":
    handle_updates()
