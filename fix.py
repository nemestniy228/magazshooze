import sqlite3, hashlib
conn = sqlite3.connect('magazshooze.db')
pwd = hashlib.md5('admin123'.encode()).hexdigest()
conn.execute('UPDATE users SET password=? WHERE id=2', (pwd,))
conn.commit()
conn.close()
print('готово', pwd)