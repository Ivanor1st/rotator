import sqlite3, json
conn = sqlite3.connect('D:/Project/rotator/rotator.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM override_state')
rows = cursor.fetchall()
for row in rows:
    print('override_state:', row)
print()
cursor.execute('SELECT * FROM app_state')
rows = cursor.fetchall()
for row in rows:
    print('app_state:', row)
conn.close()