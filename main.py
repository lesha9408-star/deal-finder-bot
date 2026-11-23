import sys
import time
import re
import logging
from zoneinfo import ZoneInfo
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BASE_DIR
from database import init_db, is_seen, mark_as_seen, get_seen_apartment_price, update_seen_price
from notifier import send_telegram_message, send_telegram_photo
from comparator import verify_and_enrich_deal
from scrapers.real_estate import get_latest_kyiv_apartments
from scrapers.groceries import get_supermarket_food_deals, get_cheap_cat_pouches
from scrapers.varus import get_varus_food_deals
from scrapers.clothing import get_branded_outlet_deals
from scrapers.kfc import get_kfc_deals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def should_check_apartments(force: bool = False) -> bool:
    if force:
        return True
    kyiv_hour = datetime.now(ZoneInfo("Europe/Kyiv")).hour
    # Strictly send apartments twice a day: at 12:00 and 20:00 Kyiv time
    return kyiv_hour in (12, 20)

def notify_apartments(max_items: int = 2, force: bool = False):
    if not should_check_apartments(force=force):
        logger.info("Пропуск квартир (отправка строго 2 раза в день: в 12:00 и 20:00 по Киеву)")
        return

    logger.info("--- Поиск квартир: Киев, ПРАВЫЙ БЕРЕГ <= 4 км от м. Олимпийская (до $40,000) ---")
    flats = get_latest_kyiv_apartments()
    sent_count = 0

    for flat in flats:
        if sent_count >= max_items:
            break

        item_id = flat["id"]
        title = flat["title"]
        price_str = flat["price"]
        location = flat["location"]
        url = flat["url"]
        source = flat["source"]
        photo = flat.get("photo_url")

        # Parse numeric price
        curr_price_num = None
        digits = re.findall(r"\d+", price_str.replace(" ", "").replace(",", ""))
        if digits:
            try:
                curr_price_num = float("".join(digits))
            except Exception:
                pass

        is_already_seen = is_seen(item_id)
        is_price_drop = False
        price_diff = 0
        old_price_num = None

        if is_already_seen:
            old_price_num = get_seen_apartment_price(item_id)
            if old_price_num and curr_price_num and curr_price_num < old_price_num:
                price_diff = old_price_num - curr_price_num
                if price_diff >= 500:  # Price dropped by at least $500 USD
                    is_price_drop = True
            if not is_price_drop:
                continue

        if is_price_drop:
            caption = (
                f"📉 <b>СНИЖЕНИЕ ЦЕНЫ НА КВАРТИРУ!</b>\n"
                f"📍 <i>{source}</i>\n\n"
                f"💰 <b>Новая цена:</b> ${curr_price_num:,.0f} <s>(${old_price_num:,.0f})</s>\n"
                f"🔥 <b>Снижение цены продавцом:</b> -${price_diff:,.0f} USD!\n"
                f"📌 <b>Локация:</b> {location}\n"
                f"📝 <b>Объект:</b> {title}\n\n"
                f"🔗 <a href='{url}'>Открыть объявление</a>"
            )
        else:
            caption = (
                f"🏠 <b>Квартира: Правый берег (до $40k)</b>\n"
                f"📍 <i>{source}</i>\n\n"
                f"💰 <b>Цена:</b> {price_str}\n"
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
            if is_price_drop:
                update_seen_price(item_id, price_str)
            else:
                mark_as_seen(item_id, source, title, price_str, url)
            sent_count += 1
            time.sleep(1.2)

    logger.info(f"Отправлено квартир/снижений цен: {sent_count}")

def notify_food_groceries(max_items: int = 3):
    logger.info("--- Поиск РЕАЛЬНО дешевых базовых продуктов (Auchan, Novus, Varus) ---")
    
    deals_auchan_novus = get_supermarket_food_deals(min_discount_percent=35)
    deals_varus = get_varus_food_deals(min_discount_percent=35)
    
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

        # Strict multi-chain verification: must be at least 25% cheaper than lowest competitor
        verification = verify_and_enrich_deal(deal_price, title, store_name=source, min_savings_percent=25)
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

def notify_cheap_cat_pouches(max_items: int = 2):
    """Notifies on cheap cat food pouches (10-14 UAH) in Auchan/supermarkets."""
    logger.info("--- Поиск дешевых паучей для кошек (до 14 ₴) ---")
    pouches = get_cheap_cat_pouches(max_price=14.5)
    sent_count = 0

    for item in pouches:
        if sent_count >= max_items:
            break

        item_id = item["id"]
        if is_seen(item_id):
            continue

        title = item["title"]
        price = item["price"]
        source = item["source"]
        url = item["url"]
        photo = item.get("photo_url")

        caption = (
            f"🐱 <b>Дешевый корм для кошек (пауч до 14 ₴)</b>\n"
            f"🏬 <i>{source}</i>\n\n"
            f"📦 <b>{title}</b>\n"
            f"💵 <b>Цена:</b> <b>{price}</b>\n\n"
            f"💡 <i>Отличная цена за порционный пауч!</i>\n\n"
            f"🛒 <a href='{url}'>Купить в магазине</a>"
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

    logger.info(f"Отправлено дешевых паучей для кошек: {sent_count}")

def notify_branded_outlet(max_items: int = 2):
    """Notifies on deep outlet liquidation discounts (Nike, Adidas, Puma, etc. >= 50%)."""
    logger.info("--- Поиск ликвидаций брендовой обуви и одежды (-50% и более) ---")
    deals = get_branded_outlet_deals(min_discount=50, max_items=max_items)
    sent_count = 0

    for deal in deals:
        if sent_count >= max_items:
            break

        item_id = deal["id"]
        if is_seen(item_id):
            continue

        title = deal["title"]
        price = deal["price"]
        old_price = deal.get("old_price")
        discount = deal.get("discount", "-50%")
        source = deal["source"]
        url = deal["url"]
        photo = deal.get("photo_url")

        caption = (
            f"👟 <b>Ликвидация / Распродажа брендов ({discount})</b>\n"
            f"🏬 <i>{source}</i>\n\n"
            f"🏷 <b>{title}</b>\n"
            f"💵 <b>Цена распродажи:</b> <b>{price}</b>"
        )
        if old_price:
            caption += f" <s>({old_price})</s>\n\n"
        else:
            caption += "\n\n"

        caption += (
            f"🔥 <i>Скидка {discount} на оригинальный бренд (остатки склада / закрытие коллекций)!</i>\n\n"
            f"🛒 <a href='{url}'>Смотреть размер и заказать</a>"
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

    logger.info(f"Отправлено ликвидаций брендовой одежды: {sent_count}")

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
    force_apartments = "--apartments" in sys.argv
    notify_food_groceries(max_items=3)
    notify_cheap_cat_pouches(max_items=1)
    notify_branded_outlet(max_items=1)
    notify_apartments(max_items=2, force=force_apartments)
    notify_kfc(max_items=1)

if __name__ == "__main__":
    run_once()
