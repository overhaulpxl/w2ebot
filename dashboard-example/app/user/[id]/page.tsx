// app/user/[id]/page.tsx
//
// Halaman detail user. Fetch GET /api/user/{id} di server, lalu tampilkan profil
// lengkap + kontrol admin per user. Deep-linkable & bisa di-share.

import Link from "next/link";
import { botGet, type UserProfile } from "@/lib/botApi";
import { ToastProvider } from "@/components/Toast";
import { Icon } from "@/components/Icon";
import { UserAdminControls } from "@/components/UserAdminControls";

export const dynamic = "force-dynamic";

function nf(n: number) {
  return n.toLocaleString("id-ID");
}

function fmtCooldown(sec: number) {
  if (sec <= 0) return "Siap";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h) return `${h}j ${m}m lagi`;
  return `${m}m lagi`;
}

export default async function UserDetailPage({ params }: { params: { id: string } }) {
  let user: UserProfile | null = null;
  let error: string | null = null;

  try {
    user = await botGet<UserProfile>(`/api/user/${params.id}`);
  } catch (e: any) {
    error = e.message;
  }

  const crypto = user ? Object.entries(user.crypto) : [];
  const rigs = user ? Object.entries(user.rigs) : [];
  const items = user ? Object.entries(user.items) : [];

  return (
    <ToastProvider>
      <div className="bg-blobs" aria-hidden="true">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
      </div>

      <div className="page">
        <Link href="/" className="btn btn-ghost" style={{ marginBottom: 20, width: "fit-content" }}>
          <Icon name="grid" size={16} />
          Kembali ke Dashboard
        </Link>

        {error && (
          <div className="card card-pad error-text" role="alert">
            Gagal memuat user: {error}
          </div>
        )}

        {user && (
          <div className="stack">
            {/* Header profil */}
            <section className="card card-pad" aria-label="Profil">
              <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
                <span
                  className="brand-mark"
                  style={{ width: 64, height: 64, fontSize: 24 }}
                  aria-hidden="true"
                >
                  {user.displayName.charAt(0).toUpperCase()}
                </span>
                <div style={{ minWidth: 0 }}>
                  <h1 style={{ fontSize: 24 }}>{user.displayName}</h1>
                  <div className="faint tnum" style={{ fontSize: 13 }}>
                    ID: {user.id}
                  </div>
                </div>
              </div>

              <div className="stat-grid stagger" style={{ marginTop: 20 }}>
                <Stat icon="trophy" label="Level" value={nf(user.level)} />
                <Stat icon="signal" label="Rank" value={user.rank ? `#${user.rank}` : "—"} />
                <Stat icon="coins" label="Koin" value={nf(user.coins)} />
                <Stat icon="activity" label="XP" value={`${nf(user.xp)} / ${nf(user.xp_to_next)}`} />
              </div>
            </section>

            {/* Aset & status */}
            <div className="admin-grid">
              <InfoCard title="Crypto" rows={crypto} empty="Tidak punya kripto." unit="" />
              <InfoCard title="Mining Rigs" rows={rigs.map(([t, c]) => [`Tier ${t}`, c])} empty="Tidak punya rig." unit="unit" />
              <InfoCard title="Items" rows={items} empty="Tas kosong." unit="x" />
            </div>

            {/* Status lain */}
            <section className="card card-pad">
              <h3 style={{ marginBottom: 16 }}>Status</h3>
              <div className="kv-grid">
                <KV label="Pet" value={user.pet ?? "—"} />
                <KV label="Total Menit VC" value={nf(user.total_vc_minutes)} />
                <KV label="Menikah dengan" value={user.married_to ? user.married_to : "Jomblo"} />
                <KV label="Achievement" value={user.achievements.length ? user.achievements.join(", ") : "—"} />
                <KV label="Cooldown Work" value={fmtCooldown(user.cooldowns.work)} />
                <KV label="Cooldown Rob" value={fmtCooldown(user.cooldowns.rob)} />
                <KV label="Cooldown Pray" value={fmtCooldown(user.cooldowns.pray)} />
                <KV label="Cooldown Curse" value={fmtCooldown(user.cooldowns.curse)} />
              </div>
            </section>

            {/* Top 3 Minigame */}
            <section className="card card-pad">
              <h3 style={{ marginBottom: 16 }}>Top 3 Minigame</h3>
              {(!user.top_games || user.top_games.length === 0) ? (
                <div className="faint">Belum ada data minigame.</div>
              ) : (
                <div className="kv-grid">
                  {user.top_games.map((g: any) => (
                    <div className="kv" key={g.game}>
                      <div className="kv-text">
                        <div className="kv-label">{g.game.charAt(0).toUpperCase() + g.game.slice(1)}</div>
                        <div className="kv-value" style={{ fontSize: 15 }}>
                          {nf(g.plays)} main &middot; {g.win_rate.toFixed(1)}% win
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* All Games Stats */}
            {user.games && Object.keys(user.games).length > 0 && (
              <section className="card card-pad">
                <h3 style={{ marginBottom: 16 }}>Statistik Minigame</h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        <th style={{ textAlign: "left", padding: "8px 12px" }}>Game</th>
                        <th style={{ textAlign: "right", padding: "8px 12px" }}>Main</th>
                        <th style={{ textAlign: "right", padding: "8px 12px" }}>Menang</th>
                        <th style={{ textAlign: "right", padding: "8px 12px" }}>Win Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(user.games).map(([game, stats]: [string, any]) => (
                        <tr key={game} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "8px 12px" }}>{game.charAt(0).toUpperCase() + game.slice(1)}</td>
                          <td className="tnum" style={{ textAlign: "right", padding: "8px 12px" }}>{nf(stats.plays ?? 0)}</td>
                          <td className="tnum" style={{ textAlign: "right", padding: "8px 12px" }}>{nf(stats.wins ?? 0)}</td>
                          <td className="tnum" style={{ textAlign: "right", padding: "8px 12px" }}>
                            {stats.plays ? ((stats.wins / stats.plays) * 100).toFixed(1) : "0.0"}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Kontrol admin */}
            <UserAdminControls userId={user.id} />
          </div>
        )}
      </div>
    </ToastProvider>
  );
}

function Stat({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className="stat">
      <div className="stat-label">
        <Icon name={icon} size={16} />
        {label}
      </div>
      <div className="stat-value tnum">{value}</div>
    </div>
  );
}

function InfoCard({
  title,
  rows,
  empty,
  unit,
}: {
  title: string;
  rows: [string, number | string][];
  empty: string;
  unit: string;
}) {
  return (
    <section className="card card-pad">
      <h3 style={{ marginBottom: 12 }}>{title}</h3>
      {rows.length === 0 ? (
        <div className="faint">{empty}</div>
      ) : (
        <div className="stack" style={{ gap: 8 }}>
          {rows.map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between" }}>
              <span className="muted">{k}</span>
              <span className="tnum" style={{ fontWeight: 600 }}>
                {typeof v === "number" ? v.toLocaleString("id-ID") : v} {unit}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="kv">
      <div className="kv-text">
        <div className="kv-label">{label}</div>
        <div className="kv-value" style={{ fontSize: 15 }}>
          {value}
        </div>
      </div>
    </div>
  );
}
