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
    "шоколад": 40.0,
    "chocolate": 40.0,
    "кава мелена": 110.0,
    "кава розчинна": 130.0,
    "чай": 35.0,
    "масло": 75.0,
    "кисломолочн": 40.0,
    "творог": 40.0,
    "простонаше": 40.0,
    "брі": 65.0,
    "brie": 65.0,
    "камамбер": 65.0,
    "camembert": 65.0,
    "сметана": 38.0,
    "кефір": 45.0,
    "молоко": 38.0,
    "макарон": 30.0,
    "цукор": 32.0,
    "олія соняшник": 55.0,
    "пауч": 13.5
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

def extract_weight_grams(text: str):
    if not text:
        return None
    text_lower = text.lower()
    m_kg = re.search(r"(\d+[\.,]?\d*)\s*(?:кг|kg)\b", text_lower)
    if m_kg:
        return float(m_kg.group(1).replace(",", ".")) * 1000.0
    m_g = re.search(r"(\d+[\.,]?\d*)\s*(?:г|g|гр|грамм|грам)\b", text_lower)
    if m_g:
        return float(m_g.group(1).replace(",", "."))
    m_ml = re.search(r"(\d+[\.,]?\d*)\s*(?:мл|ml)\b", text_lower)
    if m_ml:
        return float(m_ml.group(1).replace(",", "."))
    m_l = re.search(r"(\d+[\.,]?\d*)\s*(?:л|l)\b", text_lower)
    if m_l:
        return float(m_l.group(1).replace(",", ".")) * 1000.0
    return None

def find_best_competitor_match(raw_title: str, results: list):
    target_lower = raw_title.lower()
    target_weight = extract_weight_grams(raw_title)

    is_herring = any(k in target_lower for k in ["оселед", "селедк", "селедочк"])

    # Stop words that appear in packaging or states
    stop_words = {"філе", "маслі", "олії", "посолу", "пряного", "смак", "смаку", "напівтвердий", "твердий", "для", "під", "шматочки"}
    target_words = set(re.findall(r"\b[a-zA-Zа-яА-Яіїєґ]{3,}\b", target_lower)) - stop_words

    candidates = []
    for item in results:
        title = item.get("title", "")
        title_lower = title.lower()
        unit = item.get("unit")
        weight = item.get("weight") or extract_weight_grams(title)

        # 1. Negative fish check: herring must NEVER match sprat / salaka / etc.
        if is_herring:
            if any(bad in title_lower for bad in ["салака", "шпрот", "мойва", "сардин", "кілька", "тюлька"]):
                continue
            if not any(good in title_lower for good in ["оселед", "селед", "herring"]):
                continue

        # 2. Strict weight check: if deal is packaged (e.g. 185g, 250g), reject kg bulk / head
        if target_weight and target_weight < 800:
            if unit == "kg" and (weight is None or weight >= 900):
                continue
            if weight is not None:
                diff_pct = abs(weight - target_weight) / target_weight
                if diff_pct > 0.25:  # more than 25% difference in pack weight
                    continue

        cand_words = set(re.findall(r"\b[a-zA-Zа-яА-Яіїєґ]{3,}\b", title_lower)) - stop_words
        overlap = len(target_words & cand_words)
        weight_diff = abs(weight - target_weight) if (weight and target_weight) else 999
        candidates.append((overlap, -weight_diff, item))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_overlap, _, best_item = candidates[0]
    if best_overlap >= 1:
        return best_item
    return None

def compare_across_ukraine_stores(raw_title: str, query: str, current_store_name: str = "") -> Dict[str, Any]:
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
                    best_match = find_best_competitor_match(raw_title, data.get("results", []))
                    if best_match:
                        p_price = best_match.get("price", 0) / 100.0
                        raw_url = best_match.get("web_url", "")
                        # Ensure link is Ukrainian locale
                        web_url = raw_url.replace("/en/", "/uk/") if raw_url else ""
                        if p_price > 5 and web_url:
                            prices.append({
                                "store": store_name,
                                "title": best_match.get("title"),
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

def verify_and_enrich_deal(deal_price: float, raw_title: str, store_name: str = "", min_savings_percent: int = 25) -> Dict[str, Any]:
    # 1. Sanity check: must be within cheap deal ceiling
    if not check_price_ceiling(raw_title, deal_price):
        return {
            "is_worth_it": False,
            "reason": "Превышает ценовой потолок для дешевого товара"
        }

    search_query = clean_query_title(raw_title)
    if not search_query:
        return {"is_worth_it": False, "reason": "Невозможно выделить ключевые слова"}

    # 2. Check competitor store chains in Ukraine with exact product matching
    comp_data = compare_across_ukraine_stores(raw_title, search_query, store_name)
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
