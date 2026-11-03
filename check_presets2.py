import sqlite3, json, re
conn = sqlite3.connect('D:/Project/rotator/rotator.db')
cursor = conn.cursor()
cursor.execute('SELECT id, name, data_json FROM presets')
rows = cursor.fetchall()
for row in rows:
    data = json.loads(row[2])
    name = str(row[1])
    # Remove emojis
    name = re.sub(r'[^\x00-\x7F]+', '', name)
    print('ID: ' + str(row[0]) + ', Name: ' + name)
    chat_data = data.get('profiles', {}).get('chat', {})
    print('lock_top: ' + str(chat_data.get('lock_top')))
    print('models: ' + str(chat_data.get('models')))
    print()
conn.close()