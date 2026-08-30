import sqlite3
import datetime
def grant():
    conn = sqlite3.connect('w2ebot.db')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for uid in ['529168872696446988', '926369560821641227']:
        conn.execute(
            "INSERT OR REPLACE INTO DashboardOperatorPermission (guildId, userId, permissionClass, grantedById, status, grantedAt) VALUES (?, ?, 'DASHBOARD_SECURITY_ADMIN', 'SYSTEM', 'ACTIVE', ?)",
            ('887968847842402355', uid, now)
        )
    conn.commit()
    print("Granted DASHBOARD_SECURITY_ADMIN to both users.")
if __name__ == '__main__': grant()
