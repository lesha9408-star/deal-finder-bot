import re
import json
import logging
from typing import List, Dict, Any
import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
}

# Strict exclusion of non-essentials / sweets / junk
NON_ESSENTIAL_STOPWORDS = [
    "пудр", "шоколад", "цукерк", "конфет", "батончик", "вафл", "печив", "печень",
    "торт", "круасан", "кекс", "мафін", "маффин", "тістечк", "пирожн",
    "жуйк", "жвачк", "чіпс", "чипс", "снек", "сухарик", "грінк", "попкорн",
    "розпушувач", "дріждж", "дрожж", "ваніл", "желатин", "желе", "мармелад",
    "зефір", "зефир", "посипк", "сироп", "топінг", "топпинг", "глазур",
    "льодяник", "леденец", "драже", "пастил", "карамел", "цукат",
    "кіт", "кот", "собак", "твари", "корм", "cat", "dog", "наповнювач"
]

# Essential everyday staple keywords (dairy, meat, fish, eggs, veg, fruit, basic grains/oil)
STAPLE_KEYWORDS = [
    "кур", "індич", "яловичин", "говядин", "свин", "фарш", "філе", "стейк", "стегн", "гомілк", "крильц",
    "ковбас", "сосиск", "сардельк", "буженин", "бекон", "шинк",
    "молок", "сир", "творог", "масло", "сметан", "кефір", "йогурт", "вершк", "ряжанк",
    "яйц", "яйца",
    "риб", "сьомг", "лосос", "форел", "хек", "минтай", "оселед", "скумбрі", "тунец", "креветк", "ікр",
    "картопл", "томат", "помідор", "огірок", "моркв", "капуст", "цибул", "перець", "буряк", "часник",
    "яблук", "банан", "апельсин", "мандарин", "лимон", "грейпфрут", "груш",
    "макарон", "спагет", "паст", "крупа", "гречк", "рис", "вівсянк", "борошн", "мука",
    "олі"
]

VARUS_STAPLE_CATEGORIES = [
    "myasni-virobi-ta-yaycya",  # М'ясо та напівфабрикати
    "molochni-produkti",        # Молочні продукти
    "siri",                     # Сири
    "riba",                     # Риба та морепродукти
    "frukti-ovochi-gorihi",     # Овочі та фрукти
    "bakaliya",                 # Бакалія
    "rasprodazha"               # Спецпропозиції / акції
]

def is_staple_food(title: str) -> bool:
    t = title.lower()
    for stop in NON_ESSENTIAL_STOPWORDS:
        if stop in t:
            return False
    for staple in STAPLE_KEYWORDS:
        if staple in t:
            return True
    return False

def get_varus_food_deals(min_discount_percent: int = 25) -> List[Dict[str, Any]]:
    """Scrapes Varus directly using their public SSR catalog without requiring any user login."""
    deals = []
    seen_ids = set()

    with httpx.Client(timeout=10.0, headers=HEADERS) as client:
        for cat in VARUS_STAPLE_CATEGORIES:
            url = f"https://varus.ua/{cat}"
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue

                prefix = "window.__INITIAL_STATE__="
                start = resp.text.find(prefix)
                if start == -1:
                    continue

                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(resp.text[start + len(prefix):])

                prods = (
                    data.get("category", {}).get("products", [])
                    or data.get("special-offers", {}).get("products", [])
                )

                for p in prods:
                    name = p.get("name", "").strip()
                    if not name or not is_staple_food(name):
                        continue

                    prod_id = str(p.get("id", ""))
                    if not prod_id or prod_id in seen_ids:
                        continue

                    regular_price = float(p.get("regular_price") or 0)
                    special_price = float(p.get("special_price") or 0)

                    if not regular_price or not special_price or special_price >= regular_price:
                        continue

                    discount_pct = round((regular_price - special_price) / regular_price * 100)
                    if discount_pct < min_discount_percent:
                        continue

                    seen_ids.add(prod_id)

                    slug = p.get("url_key") or p.get("slug") or ""
                    product_url = f"https://varus.ua/{slug}" if slug else f"https://varus.ua/{cat}"
                    photo_url = f"https://varus.ua/img/product/300/300/{prod_id}"

                    deals.append({
                        "id": f"varus_{prod_id}",
                        "source": "VARUS",
                        "title": name,
                        "price": f"{special_price:.1f} ₴",
                        "price_num": special_price,
                        "old_price": f"{regular_price:.1f} ₴",
                        "discount": f"-{discount_pct}%",
                        "url": product_url,
                        "photo_url": photo_url
                    })
            except Exception as e:
                logger.error(f"Error scraping Varus category '{cat}': {e}")

    logger.info(f"Varus scraper found {len(deals)} staple deals with >={min_discount_percent}% discount")
    return deals
