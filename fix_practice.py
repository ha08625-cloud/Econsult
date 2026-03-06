import sqlite3

conn = sqlite3.connect("runtime.db")
conn.execute("DELETE FROM practices WHERE practice_id = 'test_practice'")
conn.commit()

rows = conn.execute("SELECT practice_id, name, email FROM practices").fetchall()
print("Remaining practices:")
for row in rows:
    print(f"  {row}")

conn.close()