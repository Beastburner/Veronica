import sqlite3
conn = sqlite3.connect("veronica.db")
try:
    conn.execute("ALTER TABLE memories ADD COLUMN embedding TEXT")
    conn.commit()
    print("Column added")
except Exception as e:
    print("Error:", e)
conn.close()
