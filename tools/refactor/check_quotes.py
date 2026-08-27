with open('core.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

c = 0
for i, line in enumerate(lines):
    c += line.count('"""')
    if c % 2 != 0:
        print(f"Mismatch at line {i+1}: {repr(line)}")
        break