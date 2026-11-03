import sqlite3
conn = sqlite3.connect('D:/Project/rotator/rotator.db')
cursor = conn.cursor()
cursor.execute('UPDATE app_state SET value = "null" WHERE key = "active_preset_id"')
conn.commit()
print('Active preset cleared')
conn.close()