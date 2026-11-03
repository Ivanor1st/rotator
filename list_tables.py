import sqlite3
conn = sqlite3.connect('D:/Project/rotator/rotator.db')
cursor = conn.cursor()
cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
rows = cursor.fetchall()
for row in rows:
    print(row[0])
conn.close()