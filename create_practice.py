import sqlite3
conn = sqlite3.connect("runtime.db")
conn.execute(
    "INSERT INTO practices (practice_id, name, email) VALUES (?, ?, ?)",
    ("test_practice", "Test Practice", "test@example.com")
)
conn.commit()
conn.close()
print("Done")