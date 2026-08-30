import sqlite3, datetime
def fix_7():
    conn = sqlite3.connect('w2ebot.db')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    from economy.constants import MINING_RIG_CATALOG
    if not conn.execute("SELECT 1 FROM MiningRigCatalog LIMIT 1").fetchone():
        for rig_id, (name, price, gross, maintenance) in MINING_RIG_CATALOG.items():
            conn.execute(
                "INSERT INTO MiningRigCatalog (rigDefinitionId,name,purchasePriceEcy,grossEquivalentPerDay,maintenancePriceEcy,catalogVersion,createdAt) VALUES (?,?,?,?,?,?,?)",
                (rig_id, name, price, gross, maintenance, 'mining-v1.0.0', now)
            )
        print('Phase 7 seeded.')
        conn.commit()
if __name__ == '__main__': fix_7()
