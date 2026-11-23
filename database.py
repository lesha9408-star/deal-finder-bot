import sqlite3
import re
from typing import Optional, List
from config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            title TEXT,
            price TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key TEXT NOT NULL,
            title TEXT,
            feedback_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learned_stop_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def is_seen(item_key: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM seen_items WHERE item_key = ?", (item_key,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def get_seen_apartment_price(item_key: str) -> Optional[float]:
    """Returns previously recorded numeric price if seen, else None."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT price FROM seen_items WHERE item_key = ?", (item_key,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        nums = re.findall(r"\d+", str(row[0]).replace(" ", "").replace(",", ""))
        if nums:
            try:
                return float("".join(nums))
            except Exception:
                pass
    return None

def update_seen_price(item_key: str, new_price: str):
    """Updates the recorded price when a price drop occurs."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE seen_items SET price = ? WHERE item_key = ?", (str(new_price), item_key))
    conn.commit()
    conn.close()

def mark_as_seen(item_key: str, source: str, title: str, price: str, url: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO seen_items (item_key, source, title, price, url)
        VALUES (?, ?, ?, ?, ?)
    """, (item_key, source, title, str(price), url))
    conn.commit()
    conn.close()

def save_feedback(item_key: str, title: str, feedback_type: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feedback (item_key, title, feedback_type)
        VALUES (?, ?, ?)
    """, (item_key, title, feedback_type))

    # If disliked, extract meaningful words and save as learned stop words
    if feedback_type == "dislike" and title:
        words = re.findall(r"[А-Яа-яA-Za-z]{4,}", title.lower())
        # filter out common prepositions / verbs
        ignore = {"цена", "скидка", "киев", "київ", "квартира", "продаж", "акція", "продам", "акция", "купить", "район"}
        for w in words:
            if w not in ignore:
                cursor.execute("INSERT OR IGNORE INTO learned_stop_words (word) VALUES (?)", (w,))

    conn.commit()
    conn.close()

def get_learned_stop_words() -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT word FROM learned_stop_words")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]
