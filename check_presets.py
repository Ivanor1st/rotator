import sqlite3, json
conn = sqlite3.connect('D:/Project/rotator/rotator.db')
cursor = conn.cursor()
cursor.execute('SELECT id, name, data_json FROM presets')
rows = cursor.fetchall()
for row in rows:
    data = json.loads(row[2])
    print('ID: ' + str(row[0]) + ', Name: ' + str(row[1]))
    chat_data = data.get('profiles', {}).get('chat', {})
    print('lock_top: ' + str(chat_data.get('lock_top')))
    print('models: ' + str(chat_data.get('models')))
    print()
conn.close()