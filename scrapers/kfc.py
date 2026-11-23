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

def get_kfc_deals() -> List[Dict[str, Any]]:
    deals = []
    # 1. Check KFC Coupons / Promos page
    url = "https://www.kfc.ua/news-ua/coupons"
    try:
        with httpx.Client(timeout=10.0, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                h1 = soup.find("h1")
                title = h1.text.strip() if h1 else "Шалена середа в KFC (-50%)"
                
                # Check for mention of discounts or Wednesday coupons
                paragraphs = [p.text.strip() for p in soup.find_all("p") if len(p.text.strip()) > 10]
                desc = "\n".join(paragraphs[:3])
                
                img_el = soup.find("img", src=re.compile(r"Купони|kfc", re.IGNORECASE))
                photo_url = img_el.get("src") if img_el else "https://cdn.prod.website-files.com/673f0317c93da18f13f34efc/6ab3e054a9249cac48b9e023_%D0%9D%D0%BE%D0%B2%D0%B8%D0%BD%D0%B8_%D0%9A%D1%83%D0%BF%D0%BE%D0%BD%D0%B8_.jpg"

                deals.append({
                    "id": "kfc_shalena_sereda",
                    "source": "KFC Ukraine",
                    "title": title,
                    "description": desc,
                    "discount": "до -50%",
                    "url": "https://www.kfc.ua/news-ua/coupons",
                    "photo_url": photo_url
                })
    except Exception as e:
        logger.error(f"Error checking KFC promos: {e}")
    return deals
