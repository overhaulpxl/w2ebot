import json
import os

path = 'E:\\w2ebot\\docs\\project_state.json'
with open(path, 'r', encoding='utf-8') as f:
    state = json.load(f)

# Update feature flags
for key in state['featureFlags']['value']:
    state['featureFlags']['value'][key] = True

# Update phase statuses
for phase in state['phaseStatuses']['value']:
    if 'implemented' in phase['status'] or 'ready' in phase['status']:
        phase['status'] = 'production_active'

# Also update the individual phase statuses
def activate_phase(key):
    if key in state and 'value' in state[key]:
        val = state[key]['value']
        if isinstance(val, dict):
            if 'status' in val:
                val['status'] = 'production_active'
            if 'productionEnabled' in val:
                val['productionEnabled'] = True
            if 'productionMigrated' in val:
                val['productionMigrated'] = True
            if 'productionStatus' in val:
                val['productionStatus'] = 'approved_and_active'
            if 'featureFlag' in val and isinstance(val['featureFlag'], dict):
                val['featureFlag']['default'] = True

for key in ['phase5Casino', 'phase6Crypto', 'phase7Mining', 'phase8Giveaway', 'phase9aBackendSafety', 'phase9bDashboard']:
    activate_phase(key)

with open(path, 'w', encoding='utf-8') as f:
    json.dump(state, f, indent=2)

print("Updated project_state.json successfully.")
