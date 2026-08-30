import sqlite3
for row in sqlite3.connect('w2ebot.db').execute('SELECT userId FROM DashboardIdentity'):
    print(row[0])
