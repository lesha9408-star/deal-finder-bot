import re
import logging
from typing import Dict, Any, List
import httpx
from config import DB_PATH

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
}

# Major supermarket chains in Ukraine for comparison
COMPETITOR_STORES = [
    ("482010105", "Novus"),
    ("48246415", "Auchan"),
    ("48215610", "Metro"),
    ("482800030", "EkoMarket"),
    ("48267601", "MegaMarket")
]

# CEILINGS FOR REAL "DEAL" STATUS (UAH)
PRICE_CEILINGS = {
    "шоколад": 45.0,
    "chocolate": 45.0,
    "кава мелена": 120.0,
    "кава розчинна": 150.0,
    "чай": 40.0,
    "масло": 85.0,
    "сир кисломолочний": 55.0,
    "макарон": 40.0,
    "цукор": 35.0,
    "олія соняшник": 65.0
}

def check_price_ceiling(title: str, price: float) -> bool:
    title_lower = title.lower()
    for keyword, max_allowed in PRICE_CEILINGS.items():
        if keyword in title_lower:
            if price > max_allowed:
                logger.info(f"Отвергнуто по ценовому потолку: '{title}' ({price} ₴ > {max_allowed} ₴)")
                return False
    return True

def clean_query_title(title: str) -> str:
    cleaned = re.sub(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ud800-\udbff][\udc00-\udfff]", "", title)
    cleaned = re.sub(r"(?i)розстрочка|кешбек|акція|знижка|уцінка|пошкоджен[а-я]+|суперціна|охолоджен[а-я]+", "", cleaned)
    cleaned = re.sub(r"[^\w\s\.,\d]", " ", cleaned)
    words = [w for w in cleaned.split() if len(w) > 1 and not w.isdigit()]
    return " ".join(words[:3])

def compare_across_ukraine_stores(query: str, current_store_name: str = "") -> Dict[str, Any]:
    prices = []
    with httpx.Client(timeout=8.0, headers=HEADERS) as client:
        for store_id, store_name in COMPETITOR_STORES:
            # Don't compare store against itself
            if current_store_name and store_name.lower() in current_store_name.lower():
                continue

            try:
                url = f"https://stores-api.zakaz.ua/stores/{store_id}/products/search/?q={httpx.URL(query).raw_path.decode()}"
                r = client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    for p in data.get("results", [])[:1]:
                        p_price = p.get("price", 0) / 100.0
                        raw_url = p.get("web_url", "")
                        # Ensure link is Ukrainian locale
                        web_url = raw_url.replace("/en/", "/uk/") if raw_url else ""
                        if p_price > 5 and web_url:
                            prices.append({
                                "store": store_name,
                                "title": p.get("title"),
                                "price": p_price,
                                "url": web_url
                            })
            except Exception:
                pass

    if not prices:
        return {"found": False}

    all_p = [item["price"] for item in prices]
    min_comp_price = min(all_p)
    avg_comp_price = round(sum(all_p) / len(all_p), 1)

    # Sort competitors by price ascending
    prices.sort(key=lambda x: x["price"])

    return {
        "found": True,
        "min_competitor_price": min_comp_price,
        "avg_competitor_price": avg_comp_price,
        "competitor_samples": prices
    }

def verify_and_enrich_deal(deal_price: float, raw_title: str, store_name: str = "", min_savings_percent: int = 20) -> Dict[str, Any]:
    # 1. Sanity check: must be within cheap deal ceiling
    if not check_price_ceiling(raw_title, deal_price):
        return {
            "is_worth_it": False,
            "reason": "Превышает ценовой потолок для дешевого товара"
        }

    search_query = clean_query_title(raw_title)
    if not search_query:
        return {"is_worth_it": False, "reason": "Невозможно выделить ключевые слова"}

    # 2. Check competitor store chains in Ukraine
    comp_data = compare_across_ukraine_stores(search_query, store_name)
    if not comp_data.get("found"):
        # Without proof from competitors, reject
        return {
            "is_worth_it": False,
            "reason": "Нет подтверждения цен в других сетях"
        }

    min_comp = comp_data["min_competitor_price"]
    avg_comp = comp_data["avg_competitor_price"]

    # If deal price is NOT strictly lower than lowest competitor -> REJECT
    if deal_price >= min_comp:
        return {
            "is_worth_it": False,
            "reason": f"Цена {deal_price} ₴ не ниже конкурентов ({min_comp} ₴)"
        }

    savings_vs_min = round(min_comp - deal_price, 1)
    savings_pct_vs_min = round((savings_vs_min / min_comp) * 100)

    # Must be at least min_savings_percent (20%) lower than lowest competitor in Ukraine
    if savings_pct_vs_min < min_savings_percent:
        return {
            "is_worth_it": False,
            "reason": f"Разница всего {savings_pct_vs_min}% (плюс-минус как везде)"
        }

    return {
        "is_worth_it": True,
        "has_market_data": True,
        "min_competitor_price": min_comp,
        "avg_competitor_price": avg_comp,
        "savings_uah": savings_vs_min,
        "savings_pct": savings_pct_vs_min,
        "search_query": search_query,
        "competitors": comp_data["competitor_samples"]
    }
