import sys
import time
import re
import logging
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BASE_DIR
from database import init_db, is_seen, mark_as_seen
from notifier import send_telegram_message, send_telegram_photo
from comparator import verify_and_enrich_deal
from scrapers.real_estate import get_latest_kyiv_apartments
from scrapers.groceries import get_supermarket_food_deals
from scrapers.varus import get_varus_food_deals
from scrapers.kasta import parse_kasta_query
from scrapers.kfc import get_kfc_deals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def notify_apartments(max_items: int = 2):
    logger.info("--- Поиск квартир: Киев, ПРАВЫЙ БЕРЕГ <= 4 км от м. Олимпийская (до $40,000) ---")
    flats = get_latest_kyiv_apartments()
    sent_count = 0

    for flat in flats:
        if sent_count >= max_items:
            break

        item_id = flat["id"]
        if is_seen(item_id):
            continue

        title = flat["title"]
        price = flat["price"]
        location = flat["location"]
        url = flat["url"]
        source = flat["source"]
        photo = flat.get("photo_url")

        caption = (
            f"🏠 <b>Квартира: Правый берег (до $40k)</b>\n"
            f"📍 <i>{source}</i>\n\n"
            f"💰 <b>Цена:</b> {price}\n"
            f"📌 <b>Локация:</b> {location}\n"
            f"📝 <b>Объект:</b> {title}\n\n"
            f"🔗 <a href='{url}'>Открыть объявление</a>"
        )

        success = False
        if photo:
            success = send_telegram_photo(caption, photo, item_key=item_id)
        if not success:
            success = send_telegram_message(caption, item_key=item_id)

        if success:
            mark_as_seen(item_id, source, title, price, url)
            sent_count += 1
            time.sleep(1.2)

    logger.info(f"Отправлено новых квартир: {sent_count}")

def notify_food_groceries(max_items: int = 5):
    logger.info("--- Поиск РЕАЛЬНО дешевых базовых продуктов (Auchan, Novus, Varus) ---")
    
    # 1. Fetch staple food deals from all 3 chains
    deals_auchan_novus = get_supermarket_food_deals(min_discount_percent=25)
    deals_varus = get_varus_food_deals(min_discount_percent=25)
    
    # Interleave deals from stores
    combined_deals = []
    max_len = max(len(deals_auchan_novus), len(deals_varus))
    for i in range(max_len):
        if i < len(deals_varus):
            combined_deals.append(deals_varus[i])
        if i < len(deals_auchan_novus):
            combined_deals.append(deals_auchan_novus[i])

    sent_count = 0

    for deal in combined_deals:
        if sent_count >= max_items:
            break

        item_id = deal["id"]
        if is_seen(item_id):
            continue

        title = deal["title"]
        price_str = deal["price"]
        source = deal["source"]
        deal_price = deal["price_num"]
        old_price = deal.get("old_price")
        url = deal["url"]
        photo = deal.get("photo_url")

        # Strict multi-chain verification: must be at least 20% cheaper than lowest competitor
        verification = verify_and_enrich_deal(deal_price, title, store_name=source, min_savings_percent=20)
        if not verification.get("is_worth_it"):
            continue

        min_comp = verification["min_competitor_price"]
        savings_uah = verification["savings_uah"]
        savings_pct = verification["savings_pct"]
        competitors = verification.get("competitors", [])

        caption = f"🔥 <b>РЕАЛЬНО ДЕШЕВЛЕ ВСЕЙ УКРАИНЫ (-{savings_pct}%)</b>\n"
        caption += f"🏬 <i>{source}</i>\n\n"
        caption += f"🍽 <b>Товар:</b> {title}\n"
        caption += f"💵 <b>Наша супер-цена:</b> <b>{deal_price:.1f} ₴</b>"
        if old_price:
            caption += f" <s>({old_price})</s>\n\n"
        else:
            caption += "\n\n"

        caption += (
            f"💡 <b>Анализ бота:</b> Базовый продукт повседневного рациона. "
            f"Цена перепроверена по крупным сетям Украины — это дно рынка (на {savings_uah:.1f} ₴ ниже лучшей цены конкурентов). "
            f"Рекомендуем брать!\n\n"
        )

        caption += f"⚖️ <b>Цены в других сетях (нажмите для проверки):</b>\n"
        for comp in competitors[:3]:
            c_store = comp["store"]
            c_price = comp["price"]
            c_url = comp["url"]
            caption += f"• <a href='{c_url}'>{c_store}</a>: {c_price:.1f} ₴\n"

        caption += f"\n💰 <b>Чистая экономия: {savings_uah:.1f} ₴ (-{savings_pct}% от лучшей цены конкурентов)!</b>\n\n"
        caption += f"🛒 <a href='{url}'>Купить по лучшей цене в {source}</a>"

        success = False
        if photo:
            success = send_telegram_photo(caption, photo, item_key=item_id)
        if not success:
            success = send_telegram_message(caption, item_key=item_id)

        if success:
            mark_as_seen(item_id, source, title, price_str, url)
            sent_count += 1
            time.sleep(1.5)

    logger.info(f"Отправлено проверенных супер-скидок на базовые продукты: {sent_count}")

def notify_rare_cat_food_steal(max_items: int = 1):
    deals = parse_kasta_query("корм для котів", min_discount_percent=45)
    for deal in deals[:max_items]:
        item_id = deal["id"]
        if is_seen(item_id):
            continue

        title = deal["title"]
        price = deal["price"]
        discount = deal.get("discount", "-45%")
        url = deal["url"]
        photo = deal.get("photo_url")

        caption = (
            f"🐱 <b>Редкая супер-скидка на корм ({discount})</b>\n\n"
            f"📦 <b>{title}</b>\n"
            f"💵 <b>Цена:</b> {price}\n\n"
            f"🔥 <a href='{url}'>Забрать со скидкой</a>"
        )

        success = False
        if photo:
            success = send_telegram_photo(caption, photo, item_key=item_id)
        if not success:
            success = send_telegram_message(caption, item_key=item_id)

        if success:
            mark_as_seen(item_id, "Kasta.ua", title, price, url)
            time.sleep(1.2)

def notify_kfc(max_items: int = 1):
    deals = get_kfc_deals()
    for deal in deals[:max_items]:
        item_id = deal["id"]
        if is_seen(item_id):
            continue

        title = deal["title"]
        discount = deal.get("discount", "-50%")
        desc = deal.get("description", "")
        url = deal["url"]
        photo = deal.get("photo_url")

        caption = (
            f"🍗 <b>KFC: Скидка недели {discount}</b>\n\n"
            f"🔥 <b>{title}</b>\n"
            f"ℹ️ <i>{desc}</i>\n\n"
            f"📲 <a href='{url}'>Подробнее об акции</a>"
        )

        success = False
        if photo:
            success = send_telegram_photo(caption, photo, item_key=item_id)
        if not success:
            success = send_telegram_message(caption, item_key=item_id)

        if success:
            mark_as_seen(item_id, "KFC Ukraine", title, discount, url)
            time.sleep(1.2)

def run_once():
    init_db()
    notify_food_groceries(max_items=4)
    notify_apartments(max_items=2)
    notify_rare_cat_food_steal(max_items=1)
    notify_kfc(max_items=1)

if __name__ == "__main__":
    run_once()
