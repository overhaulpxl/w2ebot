import re

with open("supabase_schema.sql", "r", encoding="utf-8") as f:
    sql = f.read()

# SQLite GLOB '*[^0-9]*' is equivalent to PostgreSQL NOT SIMILAR TO '%[^0-9]%'
# Or better, POSIX regex: !~ '[^0-9]'
sql = sql.replace("NOT GLOB '*[^0-9]*'", "!~ '[^0-9]'")

with open("supabase_schema.sql", "w", encoding="utf-8") as f:
    f.write(sql)

print("Fixed SQLite GLOB syntax to PostgreSQL Regex")