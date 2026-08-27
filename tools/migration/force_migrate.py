import subprocess
import json
import os
import sys

phases = [
    "migrate_economy_phase4.py",
    "migrate_economy_phase5.py",
    "migrate_economy_phase6.py",
    "migrate_economy_phase7.py",
    "migrate_economy_phase8.py",
    "migrate_phase9a_backend_safety.py",
    "migrate_phase9b_dashboard.py"
]

def run_phase(script_name):
    print(f"\n--- Running {script_name} ---")
    
    # Check if the script exists
    script_path = os.path.join("scripts", script_name)
    if not os.path.exists(script_path):
        print(f"Skipping {script_name} - not found.")
        return True
        
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    try:
        # Dry Run
        print("Dry run...")
        result = subprocess.run(["python", script_path, "--database", "staging/w2ebot-migrating.db", "--dry-run"], env=env, capture_output=True, text=True, check=True)
        try:
            manifest_info = json.loads(result.stdout)
            manifest_path = manifest_info.get("manifest_path")
        except:
            # If not JSON, maybe it doesn't need a manifest
            manifest_path = None
            print("No manifest found in stdout, attempting direct apply...")
            
        if manifest_path:
            print(f"Applying manifest: {manifest_path}...")
            # Apply
            subprocess.run(["python", script_path, "--database", "staging/w2ebot-migrating.db", "--apply", "--manifest", manifest_path, "--allow-staging-apply"], env=env, check=True)
            print("Applied successfully.")
        else:
            # If it doesn't use the manifest architecture, maybe just --apply works
            subprocess.run(["python", script_path, "--database", "staging/w2ebot-migrating.db", "--apply"], env=env, check=True)
            print("Applied successfully without manifest.")
            
    except subprocess.CalledProcessError as e:
        print(f"Failed at {script_name}:")
        print(e.stdout)
        print(e.stderr)
        return False
        
    return True

for p in phases:
    if not run_phase(p):
        print("Aborting due to error.")
        sys.exit(1)
        
print("\nAll migrations completed!")
