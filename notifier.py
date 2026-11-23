import httpx
import logging
import json
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

def make_feedback_keyboard(item_key: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "👍 Выгодно", "callback_data": f"like|{item_key}"},
                {"text": "👎 Не интересно", "callback_data": f"dislike|{item_key}"}
            ]
        ]
    }

def send_telegram_message(text: str, item_key: str = None, chat_id: str = None) -> bool:
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not target_chat_id:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    if item_key:
        payload["reply_markup"] = make_feedback_keyboard(item_key)

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Error sending telegram message: {e}")
        return False

def send_telegram_photo(caption: str, photo_url: str, item_key: str = None, chat_id: str = None) -> bool:
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not target_chat_id:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": target_chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    }
    if item_key:
        payload["reply_markup"] = make_feedback_keyboard(item_key)

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                return True
    except Exception:
        pass

    # Fallback to text message if photo fails
    return send_telegram_message(caption, item_key=item_key, chat_id=target_chat_id)
