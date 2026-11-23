import re
import logging
from typing import List, Dict, Any
import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
}

# Stores: Auchan Lybidska (Ocean Plaza) and Novus
STORES = [
    {
        "name": "Ашан Либідська (Ocean Plaza)",
        "store_id": "48246415",
        "categories": [
            "meat-fish-poultry-auchan",
            "dairy-and-eggs-auchan",
            "fish-and-seafood-auchan",
            "fruits-and-vegetables-auchan",
            "frozen-auchan",
            "grocery-and-sweets-auchan"
        ]
    },
    {
        "name": "NOVUS",
        "store_id": "482010105",
        "categories": [
            "meat-fish-poultry",
            "dairy-and-eggs",
            "fish-and-seafood-novus",
            "fruits-and-vegetables",
            "packets-cereals",
            "frozen"
        ]
    }
]

# Strict exclusion of sweets, powdered sugar, baking additives, junk snacks, and pet food
NON_ESSENTIAL_STOPWORDS = [
    "пудр", "шоколад", "цукерк", "конфет", "батончик", "вафл", "печив", "печень",
    "торт", "круасан", "кекс", "мафін", "маффин", "тістечк", "пирожн",
    "жуйк", "жвачк", "чіпс", "чипс", "снек", "сухарик", "грінк", "попкорн",
    "розпушувач", "дріждж", "дрожж", "ваніл", "желатин", "желе", "мармелад",
    "зефір", "зефир", "посипк", "сироп", "топінг", "топпинг", "глазур",
    "льодяник", "леденец", "драже", "пастил", "карамел", "цукат",
    "кіт", "кот", "собак", "твари", "cat", "dog", "корм", "наповнювач", "туалет для"
]

# Essential everyday staples (meat, dairy, fish, produce, basic grains/oil)
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

def is_staple_food(title: str) -> bool:
    title_lower = title.lower()
    for stop in NON_ESSENTIAL_STOPWORDS:
        if stop in title_lower:
            return False
    for staple in STAPLE_KEYWORDS:
        if staple in title_lower:
            return True
    return False

def get_supermarket_food_deals(min_discount_percent: int = 35) -> List[Dict[str, Any]]:
    deals = []
    seen_urls = set()

    with httpx.Client(timeout=12.0, headers=HEADERS) as client:
        for store in STORES:
            store_name = store["name"]
            store_id = store["store_id"]

            for cat in store["categories"]:
                url = f"https://stores-api.zakaz.ua/stores/{store_id}/categories/{cat}/products?page=1"
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    results = data.get("results", [])

                    for p in results:
                        title = p.get("title", "").strip()
                        if not is_staple_food(title):
                            continue

                        price = p.get("price", 0) / 100.0
                        old_price = p.get("old_price", 0) / 100.0
                        discount = p.get("discount", {}).get("value", 0)

                        if discount < min_discount_percent and (not old_price or (old_price - price) / old_price < (min_discount_percent / 100.0)):
                            continue

                        web_url = p.get("web_url")
                        if not web_url or web_url in seen_urls:
                            continue
                        seen_urls.add(web_url)

                        photo = p.get("image", {}).get("s350x350")
                        unit = p.get("unit", "шт")
                        eans = p.get("ean", "")
                        item_id = f"grocery_{store_id}_{eans or hash(title)}"

                        deals.append({
                            "id": item_id,
                            "source": store_name,
                            "title": title,
                            "price": f"{price:.1f} ₴",
                            "price_num": price,
                            "old_price": f"{old_price:.1f} ₴" if old_price else None,
                            "discount": f"-{discount}%" if discount else None,
                            "url": web_url.replace("/en/", "/uk/"),
                            "photo_url": photo
                        })
                except Exception as e:
                    logger.error(f"Error fetching {store_name} category {cat}: {e}")

    logger.info(f"Auchan & Novus found {len(deals)} staple deals with >={min_discount_percent}% discount")
    return deals


def get_cheap_cat_pouches(max_price: float = 14.5) -> List[Dict[str, Any]]:
    """Finds truly cheap cat food pouches (10-14 UAH) in supermarkets like Auchan."""
    pouches = []
    seen = set()

    with httpx.Client(timeout=10.0, headers=HEADERS) as client:
        # Search Auchan Lybidska
        for q in ["корм для котів пауч", "вологий корм для котів"]:
            try:
                url = f"https://stores-api.zakaz.ua/stores/48246415/products/search/?q={httpx.URL(q).raw_path.decode()}"
                r = client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    for p in data.get("results", []):
                        title = p.get("title", "")
                        price = p.get("price", 0) / 100.0
                        if price <= 0 or price > max_price:
                            continue

                        # Must be wet food / pouch
                        t_lower = title.lower()
                        if not any(k in t_lower for k in ["волог", "пауч", "wet", "шматочки", "паштет", "мус", "100g", "85g", "100г", "85г"]):
                            continue

                        web_url = p.get("web_url")
                        if not web_url or web_url in seen:
                            continue
                        seen.add(web_url)

                        old_price = p.get("old_price", 0) / 100.0
                        photo = p.get("image", {}).get("s350x350")
                        ean = p.get("ean", "")

                        pouches.append({
                            "id": f"cat_pouch_{ean or hash(title)}",
                            "source": "Ашан Либідська (Зоотовари)",
                            "title": title,
                            "price": f"{price:.1f} ₴",
                            "price_num": price,
                            "old_price": f"{old_price:.1f} ₴" if old_price else None,
                            "url": web_url.replace("/en/", "/uk/"),
                            "photo_url": photo
                        })
            except Exception as e:
                logger.error(f"Error fetching cheap cat pouches: {e}")

    return pouches
