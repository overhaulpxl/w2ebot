import re

def fix_trailing_tuples2(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split('\n')
    lines[816] = '            row = await db.fetchrow('
    lines[817] = '                "WITH user_stat AS (SELECT level, coins FROM DiscordStat WHERE id=$1) "'
    lines[818] = '                "SELECT COUNT(*) + 1 FROM DiscordStat, user_stat "'
    lines[819] = '                "WHERE DiscordStat.level > user_stat.level "'
    lines[820] = '                "OR (DiscordStat.level = user_stat.level AND DiscordStat.coins > user_stat.coins)", str(uid))'
    lines.pop(821)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

fix_trailing_tuples2("core.py")