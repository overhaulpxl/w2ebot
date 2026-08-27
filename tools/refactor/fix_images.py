import re

def fix_specific3(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("f\"SELECT {DEAL_SELECT} FROM Deal WHERE id=$1\", int(row_id),),\n        )",
                              "f\"SELECT {DEAL_SELECT} FROM Deal WHERE id=$1\", int(row_id))")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

fix_specific3("core.py")