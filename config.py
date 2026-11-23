import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9136455459:AAFbsXQJ8UFxvKtpa8FdGhq5UliqpCnx9bo")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "218157055")
DB_PATH = BASE_DIR / "deals.db"

# Real Estate Config
MAX_APARTMENT_PRICE_USD = 40000  # Updated to $40,000 as requested
MIN_APARTMENT_PRICE_USD = 18000

# Strict Left Bank exclusion
LEFT_BANK_KEYWORDS = [
    "дніпровськ", "днепровск", "деснянськ", "деснянск", "дарницьк", "дарницк",
    "позняк", "осокорк", "харківськ", "харьковск", "троєщин", "троещин",
    "лісов", "лесов", "воскресенк", "русанівк", "русановк", "березняк",
    "дврз", "биківн", "быковн", "бортнич", "лівобереж", "левобереж"
]

# User Location & Hyperlocal Stores Config
USER_PRIMARY_ADDRESS = "бульвар Миколи Міхновського, 6Б, Київ"
USER_SECONDARY_ADDRESS = "бульвар Миколи Міхновського, 7, Київ"
WALKING_DISTANCE_MAX_KM = 1.2  # Immediate walking distance on user's street / neighborhood

# Right Bank preferred target areas
RIGHT_BANK_KEYWORDS = [
    "либід", "лыбед", "демі", "деме", "печер", "голосі", "голосе", 
    "дружб", "звірин", "зверинец", "міхнов", "михнов", "антонович", 
    "васильків", "васильков", "палац україна", "дворец украина", "олімпій", "олимпий",
    "чорна гора", "черная гора", "саперне поле", "саперное", "солом'ян", "соломен",
    "шевченк", "поділ", "подол", "лук'ян", "лукъян", "татарк"
]
