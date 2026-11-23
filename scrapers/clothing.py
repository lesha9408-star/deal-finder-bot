import re
import logging
from typing import List, Dict, Any
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
}

BRAND_QUERIES = [
    "кросівки nike",
    "кросівки adidas",
    "взуття new balance",
    "куртка puma",
    "черевики timberland"
]

def get_branded_outlet_deals(min_discount: int = 50, max_items: int = 3) -> List[Dict[str, Any]]:
    """Scrapes deep liquidation / outlet discounts on expensive brand shoes and clothes."""
    deals = []
    seen_ids = set()

    with httpx.Client(timeout=12.0, headers=HEADERS, follow_redirects=True) as client:
        for q in BRAND_QUERIES:
            url = f"https://kasta.ua/uk/search/?q={httpx.URL(q).raw_path.decode()}"
            try:
                r = client.get(url)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")

                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if not href.startswith("/uk/product/"):
                        continue

                    card = a.find_parent(class_=lambda c: c and ("card" in c or "item" in c or "product" in c))
                    if not card:
                        continue

                    badge = card.find(string=re.compile(r"-\d+%"))
                    if not badge:
                        continue

                    m = re.search(r"-(\d+)%", badge)
                    if not m:
                        continue
                    disc = int(m.group(1))
                    if disc < min_discount:
                        continue

                    # Extract price
                    curr_p_el = card.find(class_=lambda c: c and any(k in c for k in ["t-sunset", "t-18", "t-bold"]))
                    old_p_el = card.find(class_=lambda c: c and "t-striked" in c)
                    curr_price = None
                    old_price = None

                    if curr_p_el:
                        c_clean = re.sub(r"[^\d]", "", curr_p_el.text)
                        if c_clean:
                            curr_price = int(c_clean)
                    if old_p_el:
                        o_clean = re.sub(r"[^\d]", "", old_p_el.text)
                        if o_clean:
                            old_price = int(o_clean)

                    if not curr_price:
                        continue

                    # Title / Description
                    title_el = card.find(class_="wrapper-properties") or card.find(class_="p__info_bottom")
                    title = title_el.text.strip().replace("\n", " ") if title_el else q.title()
                    # Clean title
                    title = re.sub(r"\s+", " ", title)

                    prod_id_match = re.search(r"/product/([0-9:]+)/", href)
                    item_id = f"brand_{prod_id_match.group(1)}" if prod_id_match else href
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    img_el = card.find("img")
                    photo_url = img_el.get("src") if img_el else None

                    deals.append({
                        "id": item_id,
                        "source": "Outlet / Розпродаж брендів",
                        "title": f"{q.upper()} | {title[:90]}",
                        "price": f"{curr_price} ₴",
                        "old_price": f"{old_price} ₴" if old_price else None,
                        "discount": f"-{disc}%",
                        "url": f"https://kasta.ua{href}",
                        "photo_url": photo_url
                    })

                    if len(deals) >= max_items:
                        return deals
            except Exception as e:
                logger.error(f"Error scraping brand query {q}: {e}")

    return deals
