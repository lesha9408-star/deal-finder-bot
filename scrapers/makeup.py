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

# Exclude decorative makeup per user preference
DECORATIVE_EXCLUDES = [
    "помада", "блиск", "туш", "пудра", "тіні", "рум'яна", "лак для нігтів", 
    "олівець", "консилер", "хайлайтер", "тональн", "підводка"
]

def get_makeup_clearance_deals(max_results: int = 15) -> List[Dict[str, Any]]:
    """
    Scrapes the official MakeUp clearance/discount section via direct search for 'уценка'.
    Extracts perfumes, skincare, diffusers, haircare, bodycare with high discounts.
    """
    url = "https://makeup.com.ua/ua/search/?q=%D1%83%D1%86%D0%B5%D0%BD%D0%BA%D0%B0"
    deals = []

    try:
        with httpx.Client(timeout=10.0, headers=HEADERS) as client:
            r = client.get(url)
            if r.status_code != 200:
                logger.error(f"MakeUp returned status {r.status_code}")
                return []

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

                # Filter out unwanted decorative cosmetics
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

                price_curr_el = c.select_one("span.Price__priceCurrent, [class*='priceCurrent']")
                curr_price_str = price_curr_el.get_text(strip=True) if price_curr_el else ""
                curr_price_m = re.search(r"(\d+[\d\s]*)", curr_price_str)
                curr_price = float(curr_price_m.group(1).replace(" ", "").replace("\xa0", "")) if curr_price_m else 0

                price_old_el = c.select_one("span.Price__priceOld, [class*='priceOld'], [class*='OldPrice']")
                old_price_str = price_old_el.get_text(strip=True) if price_old_el else ""
                old_price_m = re.search(r"(\d+[\d\s]*)", old_price_str) if old_price_str else None
                old_price = float(old_price_m.group(1).replace(" ", "").replace("\xa0", "")) if old_price_m else None

                if curr_price > 0:
                    discount_pct = 0
                    if old_price and old_price > curr_price:
                        discount_pct = round(((old_price - curr_price) / old_price) * 100)

                    deals.append({
                        "id": f"makeup_{prod_id}",
                        "title": clean_title,
                        "current_price": f"{curr_price:.0f} ₴",
                        "old_price": f"{old_price:.0f} ₴" if old_price else "",
                        "discount_percent": discount_pct,
                        "url": full_url,
                        "image_url": img_url,
                        "store": "MakeUp Уцінка",
                        "category": "Уцінка MakeUp"
                    })

                    if len(deals) >= max_results:
                        break

    except Exception as e:
        logger.error(f"Error scraping MakeUp clearance: {e}")

    return deals
