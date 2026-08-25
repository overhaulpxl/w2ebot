import re

with open('E:\\w2ebot\\README.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Disabled with Active
content = re.sub(r'\(Disabled\)', '(Active)', content)

# Change default enabled status text
content = content.replace('ECONOMY_V1_ENABLED=false', 'ECONOMY_V1_ENABLED=true')
content = content.replace('ECONOMY_PHASE2_ENABLED=false', 'ECONOMY_PHASE2_ENABLED=true')
content = content.replace('ECONOMY_PHASE3_ENABLED=false', 'ECONOMY_PHASE3_ENABLED=true')
content = content.replace('ECONOMY_PHASE4_ENABLED=false', 'ECONOMY_PHASE4_ENABLED=true')
content = content.replace('ECONOMY_PHASE5_ENABLED=false', 'ECONOMY_PHASE5_ENABLED=true')
content = content.replace('ECONOMY_PHASE6_ENABLED=false', 'ECONOMY_PHASE6_ENABLED=true')
content = content.replace('ECONOMY_PHASE7_ENABLED=false', 'ECONOMY_PHASE7_ENABLED=true')
content = content.replace('ECONOMY_PHASE8_ENABLED=false', 'ECONOMY_PHASE8_ENABLED=true')

with open('E:\\w2ebot\\README.md', 'w', encoding='utf-8') as f:
    f.write(content)
