import re
import glob

def fix_simple_tuple_leaks(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Pattern: await db.execute("...", (arg1, arg2, arg3,)\n        )
    # Fix: await db.execute("...", arg1, arg2, arg3)
    # This handles single-line tuple args with trailing comma and unmatched )
    
    content = re.sub(
        r'(await db\.(?:execute|fetchrow|fetch)\([^,]+),\s*\(([^)]+),\s*\)\s*\)',
        lambda m: m.group(1) + ', ' + m.group(2).strip() + ')',
        content
    )
    
    # Tuple wrapped with closing paren on next line
    content = re.sub(
        r'(await db\.(?:execute|fetchrow|fetch)\([^,]+),\s*\(([^)]+),\s*\)\s*\n\s*\)',
        lambda m: m.group(1) + ', ' + m.group(2).strip() + ')',
        content
    )

    # Fix "BEGIN IMMEDIATE" calls
    content = content.replace('await db.execute("BEGIN IMMEDIATE")', 'async with db.transaction():')
    content = content.replace("await db.execute('BEGIN IMMEDIATE')", 'async with db.transaction():')
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
fix_simple_tuple_leaks("core.py")