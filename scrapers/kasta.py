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

DEFAULT_QUERIES = [
    "корм для котів",
    "побутова хімія",
    "кава в зернах"
]

def parse_kasta_query(query: str, min_discount_percent: int = 15) -> List[Dict[str, Any]]:
    results = []
    url = f"https://kasta.ua/uk/search/?q={httpx.URL(query).raw_path.decode()}"
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                logger.error(f"Kasta returned status {resp.status_code} for query {query}")
                return results

            soup = BeautifulSoup(resp.text, "html.parser")
            seen_links = set()

            for a in soup.find_all("a", href=True):
                href = a["href"].split("#")[0]
                if not href.startswith("/uk/product/"):
                    continue
                if href in seen_links:
                    continue
                seen_links.add(href)

                card = a.find_parent(class_=lambda c: c and ("item" in c or "card" in c or "product" in c))
                if not card:
                    card = a.parent.parent

                # Title
                title_el = card.find(class_="wrapper-properties") or card.find(class_="p__info_bottom")
                title = title_el.text.strip() if title_el else ""
                if not title:
                    for sp in card.find_all(["span", "p"]):
                        if len(sp.text.strip()) > 15 and "₴" not in sp.text:
                            title = sp.text.strip()
                            break

                if not title or len(title) < 5:
                    continue

                # Old price (striked)
                old_p_el = card.find(class_=lambda c: c and "t-striked" in c)
                old_price = None
                if old_p_el:
                    old_p_clean = re.sub(r"[^\d]", "", old_p_el.text)
                    if old_p_clean:
                        old_price = int(old_p_clean)

                # Current price
                curr_p_el = card.find(class_=lambda c: c and any(k in c for k in ["t-sunset", "t-18", "t-bold"]))
                curr_price = None
                if curr_p_el:
                    curr_p_clean = re.sub(r"[^\d]", "", curr_p_el.text)
                    if curr_p_clean:
                        curr_price = int(curr_p_clean)

                # If prices not found via classes, search text for currency signs
                if not curr_price:
                    all_prices = [int(p) for p in re.findall(r"(\d+)\s*₴", card.text)]
                    if all_prices:
                        curr_price = min(all_prices)
                        if len(all_prices) > 1:
                            old_price = max(all_prices)

                # Calculate discount
                discount_percent = 0
                if old_price and curr_price and old_price > curr_price:
                    discount_percent = round((old_price - curr_price) / old_price * 100)

                # Also check badge like "-30%"
                badge = card.find(string=re.compile(r"-\d+%"))
                if badge:
                    b_match = re.search(r"-(\d+)%", badge)
                    if b_match:
                        discount_percent = max(discount_percent, int(b_match.group(1)))

                # Photo
                img_el = card.find("img")
                photo_url = img_el.get("src") if img_el else None

                prod_id_match = re.search(r"/product/([0-9:]+)/", href)
                item_id = f"kasta_{prod_id_match.group(1)}" if prod_id_match else href
                full_url = "https://kasta.ua" + href

                if discount_percent >= min_discount_percent:
                    results.append({
                        "id": item_id,
                        "source": "Kasta.ua",
                        "title": title,
                        "price": f"{curr_price} ₴" if curr_price else "Акційна ціна",
                        "old_price": f"{old_price} ₴" if old_price else None,
                        "discount": f"-{discount_percent}%" if discount_percent else None,
                        "url": full_url,
                        "photo_url": photo_url
                    })
    except Exception as e:
        logger.error(f"Error parsing Kasta query {query}: {e}")
    return results

def get_latest_kasta_deals(min_discount: int = 20) -> List[Dict[str, Any]]:
    all_deals = []
    for q in DEFAULT_QUERIES:
        deals = parse_kasta_query(q, min_discount_percent=min_discount)
        all_deals.extend(deals)
    return all_deals
