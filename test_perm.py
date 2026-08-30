import sqlite3
for row in sqlite3.connect('w2ebot.db').execute('SELECT * FROM DashboardOperatorPermission'):
    print(row)
