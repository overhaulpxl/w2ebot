import glob
import re

files_to_check = glob.glob('E:\\w2ebot\\cogs\\*.py') + ['E:\\w2ebot\\w2e_help.py']

replacements = [
    ("Casino V1", "Casino"),
    ("Crypto Market V1", "Crypto Market"),
    ("Crypto V1", "Crypto"),
    ("Mining V1", "Mining"),
    ("Giveaway V1", "Giveaway"),
    ("Economy V1", "Economy"),
]

for file_path in files_to_check:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for old, new in replacements:
        new_content = new_content.replace(old, new)
        
    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {file_path}")

print("V1 references removed.")
