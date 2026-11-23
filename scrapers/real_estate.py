import re
import math
import logging
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from config import MIN_APARTMENT_PRICE_USD, MAX_APARTMENT_PRICE_USD
from database import get_learned_stop_words

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
}

# GPS coordinates of Metro Olimpiiska
OLIMPIISKA_LAT = 50.4322
OLIMPIISKA_LON = 30.5161
MAX_RADIUS_KM = 4.0

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# General stop words (installments, rooms, parking, basements, rentals, commercial)
BASE_STOP_WORDS = [
    "перший внесок", "первый взнос", "розстрочка", "рассрочка", "розтермінування",
    "кімната", "кімнати", "комната", "комнаты", "підселення", "подселение", "частина", "доля",
    "цоколь", "цокольний", "паркінг", "паркинг", "гараж", "комора", "кладовка",
    "підвальне", "подвальное", "нежитлове", "нежилое", "оренда", "аренда", "здається", "сдается",
    "офіс", "офис", "приміщення", "помещение", "склад", "кабінет",
    "ракетн", "олімпійське містечко", "панорамне"
]

SUBURBS = [
    "бровар", "ірпін", "ирпен", "буча", "борисп", "вишнев", "вишгород",
    "софіївськ", "софиевск", "петропавлів", "петропавлов", "коцюбинськ",
    "крюківщин", "крюковщин", "гостомель", "гаврилівк", "чубинськ"
]

# Strict blacklist (> 4.0 km from Olimpiiska or Left Bank)
BEYOND_4KM_KEYWORDS = [
    # Left bank
    "дніпровськ", "днепровск", "деснянськ", "деснянск", "дарницьк", "дарницк",
    "позняк", "осокорк", "харківськ", "харьковск", "троєщин", "троещин",
    "лісов", "лесов", "воскресенк", "русанівк", "русановк", "березняк",
    "дврз", "биківн", "быковн", "бортнич", "лівобереж", "левобереж",
    # Right bank > 4 km
    "відрадн", "отрадн", "гавел", "стражеск", "медмістеч", "медгородок",
    "лук'ян", "лукъян", "дорогожич", "шуляв", "політех", "кпі", "політехн",
    "виставков", "вднг", "іподром", "теремк", "заболотн", "сирець", "сирец",
    "куренів", "куренев", "виноградар", "борщаг", "святошин", "академмістеч",
    "оболон", "мінськ", "героїв дніпр", "корчуват", "мишоловк", "пирогів",
    "метро васильківська", "м. васильківська", "вул. олімпійська"
]

# Strict whitelist (<= 4.0 km from Olimpiiska)
WITHIN_4KM_KEYWORDS = [
    "олімпій", "олимпий", "палац спорт", "дворец спорт", "українських геро", "льва толст",
    "кловськ", "палац україна", "дворец украина", "театральн", "університет", "университет",
    "золоті ворот", "печерськ", "печерск", "хрещатик", "крещатик", "майдан",
    "либідськ", "лыбедск", "вокзальн", "арсенальн", "звіринецьк", "зверинец", "дружби народ",
    "деміїв", "демеев", "поштов", "контрактов", "протасів яр", "протасов", "батиєва",
    "нововокзальн", "солом'янська площ", "соломенская площ", "антонович", "велика васильків",
    "большая васильков", "саксаганськ", "жилянськ", "володимирськ", "владимирск", "руставелі",
    "еспланадн", "басейн", "коновальц", "щорса", "тютюнник", "барбюс", "предславин", "ямськ",
    "малевич", "боженк", "чорна гор", "черная гор", "саперне пол", "ділов", "деловая",
    "федоров", "лабораторн", "липківськ", "кудряшов", "мокра"
]

def is_clean_listing(title: str, description: str = "") -> bool:
    text = f"{title} {description}".lower()
    for sw in BASE_STOP_WORDS:
        if sw in text:
            return False
    learned = get_learned_stop_words()
    for lw in learned:
        if lw in text:
            return False
    return True

def is_within_4km_of_olimpiiska(title: str, location: str, lat: Optional[float] = None, lon: Optional[float] = None) -> (bool, Optional[float]):
    combined = f"{title} {location}".lower()

    # Must be in Kyiv, not suburbs
    for sub in SUBURBS:
        if sub in combined:
            return (False, None)

    # If exact GPS coordinates exist, check distance to Olimpiiska
    if lat and lon:
        dist = haversine_km(OLIMPIISKA_LAT, OLIMPIISKA_LON, lat, lon)
        return (dist <= MAX_RADIUS_KM, round(dist, 1))

    # Reject if outside 4 km or Left Bank
    for beyond in BEYOND_4KM_KEYWORDS:
        if beyond in combined:
            return (False, None)

    # Accept if matches whitelist <= 4 km
    for within in WITHIN_4KM_KEYWORDS:
        if within in combined:
            return (True, None)

    return (False, None)

def parse_olx_apartments() -> List[Dict[str, Any]]:
    results = []
    # Targeted queries strictly near Olimpiiska (<= 4km) up to $40,000
    urls = [
        f"https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/kiev/q-%D0%BE%D0%BB%D1%96%D0%BC%D0%BF%D1%96%D0%B9%D1%81%D1%8C%D0%BA%D0%B0/?currency=USD&search%5Bfilter_float_price%3Afrom%5D={MIN_APARTMENT_PRICE_USD}&search%5Bfilter_float_price%3Ato%5D={MAX_APARTMENT_PRICE_USD}",
        f"https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/kiev/q-%D0%BB%D0%B8%D0%B1%D1%96%D0%B4%D1%81%D1%8C%D0%BA%D0%B0/?currency=USD&search%5Bfilter_float_price%3Afrom%5D={MIN_APARTMENT_PRICE_USD}&search%5Bfilter_float_price%3Ato%5D={MAX_APARTMENT_PRICE_USD}",
        f"https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/kiev/q-%D0%B4%D0%B5%D0%BC%D1%96%D1%97%D0%B2%D0%BA%D0%B0/?currency=USD&search%5Bfilter_float_price%3Afrom%5D={MIN_APARTMENT_PRICE_USD}&search%5Bfilter_float_price%3Ato%5D={MAX_APARTMENT_PRICE_USD}",
        f"https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/kiev/q-%D0%BF%D0%B5%D1%87%D0%B5%D1%80%D1%81%D1%8C%D0%BA/?currency=USD&search%5Bfilter_float_price%3Afrom%5D={MIN_APARTMENT_PRICE_USD}&search%5Bfilter_float_price%3Ato%5D={MAX_APARTMENT_PRICE_USD}"
    ]

    seen_ids = set()
    with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("div", {"data-cy": "l-card"})
                for card in cards:
                    t_el = card.find("h4")
                    p_el = card.find("p", {"data-testid": "ad-price"})
                    a_el = card.find("a", href=True)
                    loc_el = card.find("p", {"data-testid": "location-date"})
                    img_el = card.find("img")

                    if not (t_el and p_el and a_el):
                        continue

                    title = t_el.text.strip()
                    price_str = p_el.text.strip()
                    link = a_el["href"]
                    if link.startswith("/"):
                        link = "https://www.olx.ua" + link
                    link = link.split("?")[0]

                    ad_id_match = re.search(r"-ID([a-zA-Z0-9]+)\.html", link)
                    item_id = f"olx_{ad_id_match.group(1)}" if ad_id_match else link
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    location = loc_el.text.strip() if loc_el else "Київ"
                    photo_url = img_el.get("src") if img_el else None

                    price_clean = re.sub(r"[^\d]", "", price_str)
                    if not price_clean:
                        continue
                    price_num = int(price_clean)

                    if price_num < MIN_APARTMENT_PRICE_USD or price_num > MAX_APARTMENT_PRICE_USD:
                        continue

                    # Filter obvious fake luxury (e.g. 130m2 in Novopecherski Lypky for $35k is fake)
                    if "новопечерськ" in title.lower() and price_num < 80000:
                        continue

                    if not is_clean_listing(title):
                        continue

                    is_ok, dist = is_within_4km_of_olimpiiska(title, location)
                    if not is_ok:
                        continue

                    results.append({
                        "id": item_id,
                        "source": "OLX.ua",
                        "title": title,
                        "price": f"{price_num:,} $",
                        "price_num": price_num,
                        "location": location,
                        "distance_km": dist,
                        "url": link,
                        "photo_url": photo_url
                    })
            except Exception as e:
                logger.error(f"Error parsing OLX: {e}")
    return results

def parse_rieltor_apartments() -> List[Dict[str, Any]]:
    results = []
    url = f"https://rieltor.ua/flats-sale/?price_min={MIN_APARTMENT_PRICE_USD}&price_max={MAX_APARTMENT_PRICE_USD}&currency=2&sort=bydate"
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all(class_="catalog-card")
            for card in cards:
                price_el = card.find(class_="catalog-card-price-title")
                address_el = card.find(class_="catalog-card-address")
                links = [a["href"] for a in card.find_all("a", href=True) if "/flats-sale/view/" in a["href"]]
                img_el = card.find("img")

                if not (price_el and address_el and links):
                    continue

                link = links[0]
                if link.startswith("/"):
                    link = "https://rieltor.ua" + link

                id_match = re.search(r"/view/(\d+)/", link)
                item_id = f"rieltor_{id_match.group(1)}" if id_match else link

                price_text = price_el.text.strip()
                price_clean = re.sub(r"[^\d]", "", price_text)
                if not price_clean:
                    continue
                price_num = int(price_clean)

                if price_num < MIN_APARTMENT_PRICE_USD or price_num > MAX_APARTMENT_PRICE_USD:
                    continue

                location = address_el.text.strip()
                title = f"Квартира: {location}"

                if not is_clean_listing(title):
                    continue

                is_ok, dist = is_within_4km_of_olimpiiska(title, location)
                if not is_ok:
                    continue

                photo_url = img_el.get("src") if img_el else None

                results.append({
                    "id": item_id,
                    "source": "Rieltor.ua",
                    "title": title,
                    "price": f"{price_num:,} $",
                    "price_num": price_num,
                    "location": location,
                    "distance_km": dist,
                    "url": link,
                    "photo_url": photo_url
                })
    except Exception as e:
        logger.error(f"Error parsing Rieltor: {e}")
    return results

def get_latest_kyiv_apartments() -> List[Dict[str, Any]]:
    all_flats = []
    all_flats.extend(parse_olx_apartments())
    all_flats.extend(parse_rieltor_apartments())
    return all_flats
