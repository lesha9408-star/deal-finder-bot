import logging
import re
from typing import List, Dict, Any
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
}

# Strict exclusion of female decorative cosmetics, glitter, shimmer, etc.
DECORATIVE_EXCLUDES = [
    "помада", "блиск", "туш", "пудра", "тіні", "рум'яна", "лак для нігтів", 
    "олівець", "консилер", "хайлайтер", "тональн", "підводка", "шиммер", "шимер",
    "блестки", "блёстки", "жіноч", "женск", "макіяж", "сережки", "плаття", "спідниця",
    "для губ", "для вій", "манікюр", "педикюр", "браслет"
]

MEN_AND_UNISEX_QUERIES = [
    "уцінка чоловікам", "уцінка men", "розпродаж чоловікам", "уцінка парфуми чоловічі",
    "уцінка гоління", "уцінка дезодорант", "уцінка дифузор", "уцінка шампунь чоловічий",
    "уцінка гель для душу", "уцінка тканинна маска", "уцінка маска для обличчя",
    "уцінка догляд за обличчям", "уцінка крем для обличчя"
]

def get_makeup_clearance_deals(max_results: int = 10, min_discount: int = 40) -> List[Dict[str, Any]]:
    """
    Scrapes MakeUp clearance & liquidation deals specifically tailored for men/unisex.
    Filters out women's cosmetics, glitter, shimmers.
    Sorts by highest discount percentage.
    """
    all_items = {}

    try:
        with httpx.Client(timeout=10.0, headers=HEADERS) as client:
            for q in MEN_AND_UNISEX_QUERIES:
                url = f"https://makeup.com.ua/ua/search/?q={q}"
                try:
                    r = client.get(url)
                    if r.status_code != 200:
                        continue

                    soup = BeautifulSoup(r.text, "lxml")
                    cards = soup.select("div.ProductCard__card")

                    for c in cards:
                        title_el = c.select_one("a.ProductCard__title")
                        sub_title = c.select_one("div.ProductCard__subTitle")
                        if not title_el:
                            continue

                        raw_title = title_el.get_text(strip=True)
                        if sub_title:
                            raw_title += " " + sub_title.get_text(strip=True)

                        clean_title = raw_title.replace("*", "").strip()
                        title_lower = clean_title.lower()

                        if any(ex in title_lower for ex in DECORATIVE_EXCLUDES):
                            continue

                        href = title_el.get("href", "")
                        if not href:
                            continue

                        prod_id_match = re.search(r"/product/(\d+)/", href)
                        prod_id = prod_id_match.group(1) if prod_id_match else href
                        full_url = f"https://makeup.com.ua{href}" if not href.startswith("http") else href

                        img_el = c.select_one("img")
                        img_url = (img_el.get("src") or img_el.get("data-src")) if img_el else ""

                        p_curr_el = c.select_one("span.Price__priceCurrent, [class*='priceCurrent']")
                        curr_price = 0
                        if p_curr_el:
                            m = re.search(r"(\d+[\d\s]*)", p_curr_el.get_text())
                            if m:
                                curr_price = float(m.group(1).replace(" ", "").replace("\xa0", ""))

                        p_old_el = c.select_one("span.Price__priceOld, [class*='priceOld']")
                        old_price = None
                        if p_old_el:
                            m = re.search(r"(\d+[\d\s]*)", p_old_el.get_text())
                            if m:
                                old_price = float(m.group(1).replace(" ", "").replace("\xa0", ""))

                        discount_pct = 0
                        if old_price and old_price > curr_price:
                            discount_pct = round(((old_price - curr_price) / old_price) * 100)

                        if curr_price > 0 and discount_pct >= min_discount:
                            if full_url not in all_items or discount_pct > all_items[full_url]["discount_percent"]:
                                all_items[full_url] = {
                                    "id": f"makeup_{prod_id}",
                                    "title": clean_title,
                                    "current_price": f"{curr_price:.0f} ₴",
                                    "current_price_num": curr_price,
                                    "old_price": f"{old_price:.0f} ₴" if old_price else "",
                                    "old_price_num": old_price,
                                    "discount_percent": discount_pct,
                                    "url": full_url,
                                    "image_url": img_url,
                                    "store": "MakeUp",
                                    "category": "Уцінка / Розпродаж"
                                }
                except Exception as err:
                    logger.warning(f"Error querying {q}: {err}")

    except Exception as e:
        logger.error(f"Error scraping MakeUp: {e}")

    # Sort strictly by highest discount percentage descending
    sorted_deals = sorted(all_items.values(), key=lambda x: (x["discount_percent"], x["old_price_num"] or 0), reverse=True)
    return sorted_deals[:max_results]
