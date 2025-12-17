
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, create_engine, select, func
from models import Product
from config import DB_URL

# Debug raw sqlite
import sqlite3
from config import DB_PATH

def inspect():
    print(f"Inspecting DB at {DB_PATH}")
    if not DB_PATH.exists():
        print("DB file does not exist!")
        return

    # Raw SQL check
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM product")
    count = cursor.fetchone()[0]
    print(f"Raw SQLite count: {count}")
    
    cursor.execute("SELECT name, source_url FROM product LIMIT 5")
    print("First 5 items:")
    for row in cursor.fetchall():
        print(row)
    conn.close()

if __name__ == "__main__":
    inspect()
