// components/DashboardShell.tsx
//
// CRM-style shell: sidebar berkategori + topbar + konten per-section.
// Data dibaca di server (page.tsx) lalu dioper ke sini; shell hanya urus
// navigasi kategori (client-side) tanpa fetch ulang.
"use client";

import { useState } from "react";
import { Icon } from "./Icon";
import { AdminPanel } from "./AdminPanel";
import { AnnounceSettings } from "./AnnounceSettings";
import { Analytics } from "./Analytics";
import { AuditLog } from "./AuditLog";
import { UserModal } from "./UserModal";
import { useToast } from "./Toast";
import type {
  SummaryResponse,
  LeaderboardResponse,
  BotStats,
  Channel,
  AnnounceConfig,
  MarketData,
  LevelDistribution,
  MarketplaceV1Status,
} from "@/lib/botApi";

type SectionId = "overview" | "stats" | "analytics" | "players" | "economy" | "server" | "audit";

const NAV: { group: string; items: { id: SectionId; label: string; icon: any }[] }[] = [
  {
    group: "Monitoring",
    items: [
      { id: "overview", label: "Ringkasan", icon: "grid" },
      { id: "stats", label: "Statistik Bot", icon: "activity" },
      { id: "analytics", label: "Analitik", icon: "signal" },
      { id: "players", label: "Pemain", icon: "users" },
      { id: "economy", label: "Ekonomi", icon: "coins" },
    ],
  },
  {
    group: "Kontrol",
    items: [
      { id: "server", label: "Server & Admin", icon: "dragon" },
      { id: "audit", label: "Audit Log", icon: "terminal" },
    ],
  },
];

function nf(n: number) {
  return n.toLocaleString("id-ID");
}

export function DashboardShell({
  summary,
  leaderboard,
  botStats,
  channels,
  announceConfig,
  market,
  levels,
  marketplace,
  casino,
  loadError,
}: {
  summary: SummaryResponse | null;
  leaderboard: LeaderboardResponse | null;
  botStats: BotStats | null;
  channels: Channel[];
  announceConfig: AnnounceConfig | null;
  market: MarketData | null;
  levels: LevelDistribution | null;
  marketplace: MarketplaceV1Status | null;
  casino: import("@/lib/botApi").CasinoV1Status | null;
  loadError: string | null;
}) {
  const [section, setSection] = useState<SectionId>("overview");
  const [navOpen, setNavOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  const titles: Record<SectionId, string> = {
    overview: "Ringkasan",
    stats: "Statistik Bot",
    analytics: "Analitik",
    players: "Pemain",
    economy: "Ekonomi",
    server: "Server & Admin",
    audit: "Audit Log",
  };

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className={`sidebar${navOpen ? " open" : ""}`} aria-label="Navigasi utama">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            W2
          </span>
          <div>
            <strong style={{ fontSize: 15 }}>W2E Admin</strong>
            <div className="faint" style={{ fontSize: 12 }}>
              Control Center
            </div>
          </div>
        </div>

        <nav className="stack" style={{ gap: 20 }}>
          {NAV.map((g) => (
            <div className="nav-group" key={g.group}>
              <div className="nav-group-label">{g.group}</div>
              {g.items.map((it) => (
                <button
                  key={it.id}
                  className="nav-item"
                  aria-current={section === it.id ? "page" : undefined}
                  onClick={() => {
                    setSection(it.id);
                    setNavOpen(false);
                  }}
                >
                  <Icon name={it.icon} size={18} />
                  {it.label}
                  <span className="nav-accent" aria-hidden="true" />
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="faint" style={{ fontSize: 12, marginTop: "auto" }}>
          {summary ? (
            <span className={summary.boss_active ? "badge badge-on" : "badge badge-off"}>
              <Icon name="dragon" size={13} />
              {summary.boss_active ? "Boss aktif" : "Tidak ada boss"}
            </span>
          ) : null}
        </div>
      </aside>

      {/* Scrim untuk mobile */}
      <div
        className={`sidebar-scrim${navOpen ? " open" : ""}`}
        onClick={() => setNavOpen(false)}
        aria-hidden="true"
      />

      {/* Main */}
      <div className="main">
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              className="menu-btn"
              onClick={() => setNavOpen((v) => !v)}
              aria-label="Buka menu navigasi"
            >
              <Icon name="menu" size={20} />
            </button>
            <h1>{titles[section]}</h1>
          </div>
          {summary && (
            <span className="faint" style={{ fontSize: 13 }}>
              {nf(summary.member_count)} member
            </span>
          )}
        </header>

        <main className="content" id="main-content" tabIndex={-1}>
          {loadError && (
            <div
              className="card card-pad"
              role="alert"
              style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
            >
              Gagal memuat data bot: {loadError}
              <div className="helper" style={{ marginTop: 8 }}>
                Pastikan bot menyala, <code>BOT_API_URL</code> benar, lalu refresh.
              </div>
            </div>
          )}

          {/* key={section} memicu re-mount → animasi crossfade+rise tiap ganti kategori */}
          <div key={section} className="section-anim">
            {section === "overview" && <Overview summary={summary} />}
            {section === "stats" && <BotStatsView stats={botStats} loadError={loadError} />}
            {section === "analytics" && <Analytics market={market} levels={levels} marketplace={marketplace} casino={casino} />}
            {section === "players" && <Players leaderboard={leaderboard} loadError={loadError} onSelectUser={setSelectedUserId} />}
            {section === "economy" && <Economy summary={summary} />}
            {section === "server" && (
              <ServerAdmin channels={channels} announceConfig={announceConfig} />
            )}
            {section === "audit" && <AuditLog />}
          </div>
        </main>
      </div>

      {/* User profile modal */}
      {selectedUserId && (
        <UserModal userId={selectedUserId} onClose={() => setSelectedUserId(null)} />
      )}
    </div>
  );
}

// ── Sections ─────────────────────────────────────────────────────────────────

function StatCard({
  icon,
  label,
  value,
}: {
  icon: any;
  label: string;
  value: string;
}) {
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

function Overview({ summary }: { summary: SummaryResponse | null }) {
  if (!summary) return null;
  return (
    <>
      <section className="stat-grid stagger" aria-label="Ringkasan server">
        <StatCard icon="users" label="Member" value={nf(summary.member_count)} />
        <StatCard icon="mic" label="Di Voice" value={nf(summary.members_in_voice)} />
        <StatCard icon="vault" label="Kas (Treasury)" value={nf(summary.treasury_balance)} />
        <StatCard
          icon="coins"
          label="Total Koin Beredar"
          value={nf(summary.total_coins_in_circulation)}
        />
      </section>
      <div className="card card-pad">
        <h3 style={{ marginBottom: 8 }}>Status</h3>
        <p className="muted" style={{ margin: 0 }}>
          Boss raid:{" "}
          <span className={summary.boss_active ? "badge badge-on" : "badge badge-off"}>
            <Icon name="dragon" size={13} />
            {summary.boss_active ? "Aktif" : "Tidak aktif"}
          </span>
        </p>
      </div>
    </>
  );
}

function Players({
  leaderboard,
  loadError,
  onSelectUser,
}: {
  leaderboard: LeaderboardResponse | null;
  loadError: string | null;
  onSelectUser: (id: string) => void;
}) {
  const [search, setSearch] = useState("");

  function go() {
    const id = search.trim();
    if (/^\d+$/.test(id)) onSelectUser(id);
  }

  return (
    <div className="stack">
      <section className="card card-pad">
        <label className="label" htmlFor="player-search">
          Cari pemain (Discord ID)
        </label>
        <div className="row" style={{ marginTop: 6 }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <input
              id="player-search"
              className="input tnum"
              inputMode="numeric"
              placeholder="cth. 529168872696446988"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && go()}
            />
          </div>
          <button className="btn btn-primary" onClick={go} disabled={!/^\d+$/.test(search.trim())}>
            <Icon name="users" size={16} />
            Lihat Profil
          </button>
        </div>
        <span className="helper">Klik baris leaderboard atau masukkan ID untuk buka profil.</span>
      </section>

      <div className="card">
        {leaderboard && leaderboard.entries.length > 0 ? (
          <table className="lb">
            <caption
              className="faint"
              style={{ textAlign: "left", padding: "12px 16px 0", fontSize: 12 }}
            >
              Top {leaderboard.entries.length} pemain berdasarkan koin
            </caption>
            <thead>
              <tr>
                <th style={{ width: 60 }}>#</th>
                <th>Pemain</th>
                <th className="num">Level</th>
                <th className="num">Koin</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.entries.map((u) => (
                <tr
                  key={u.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => onSelectUser(u.id)}
                >
                  <td>
                    <span className={`rank${u.rank <= 3 ? " rank-" + u.rank : ""}`}>{u.rank}</span>
                  </td>
                  <td>{u.displayName}</td>
                  <td className="num tnum">{u.level}</td>
                  <td className="num tnum">{nf(u.coins)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          !loadError && <div className="card-pad faint">Belum ada data pemain.</div>
        )}
      </div>
    </div>
  );
}

function Economy({ summary }: { summary: SummaryResponse | null }) {
  return (
    <>
      {summary && (
        <section className="stat-grid stagger" aria-label="Statistik ekonomi">
          <StatCard icon="vault" label="Kas (Treasury)" value={nf(summary.treasury_balance)} />
          <StatCard
            icon="coins"
            label="Total Koin Beredar"
            value={nf(summary.total_coins_in_circulation)}
          />
        </section>
      )}
      {summary?.v1_supply && (
        <section className="card card-pad stack" aria-label="Economy V1 Phase 1 supply">
          <h3>Economy V1 Phase 1 {summary.v1_enabled ? "(Staging Aktif)" : "(Belum Diaktifkan)"}</h3>
          {(["ETM", "ECY"] as const).map((currency) => {
            const supply = summary.v1_supply![currency];
            return (
              <div key={currency} className="stat-grid">
                <StatCard icon="coins" label={`${currency} Net Issued`} value={nf(supply.net_issued_supply)} />
                <StatCard icon="coins" label={`${currency} Circulating`} value={nf(supply.circulating_supply)} />
                <StatCard icon="vault" label={`${currency} Locked Reserve`} value={nf(supply.non_circulating_supply)} />
                <StatCard icon="vault" label={`${currency} Burned`} value={nf(supply.burned_supply)} />
              </div>
            );
          })}
          <span className={summary.v1_supply.ledger_zero_sum ? "badge badge-on" : "badge badge-off"}>
            Ledger {summary.v1_supply.ledger_zero_sum ? "seimbang" : "tidak seimbang"}
          </span>
        </section>
      )}
      <AdminPanel only="user" />
    </>
  );
}

function ServerAdmin({
  channels,
  announceConfig,
}: {
  channels: Channel[];
  announceConfig: AnnounceConfig | null;
}) {
  return (
    <div className="stack">
      <AnnounceSettings channels={channels} config={announceConfig} />
      <AdminPanel only="server" />
      <ResetAllPlayers />
    </div>
  );
}

function ResetAllPlayers() {
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);

  async function doReset() {
    setBusy(true);
    try {
      const res = await fetch("/api/admin/reset-all-players", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `Gagal (${res.status})`);
      toast("success", `Reset berhasil: ${data.players_reset} pemain direset.`);
      setConfirm(false);
    } catch (e: any) {
      toast("error", e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card card-pad stack" aria-labelledby="reset-all">
      <h3 id="reset-all">Reset All Players</h3>
      <p className="helper" style={{ margin: 0 }}>
        Reset semua data pemain (koin, XP, level, items, crypto, rigs, achievements, marriage, dll)
        ke kondisi awal. Settingan bot (announce channels, config, treasury, market) TIDAK terpengaruh.
      </p>
      {!confirm ? (
        <button className="btn btn-danger" onClick={() => setConfirm(true)}>
          <Icon name="close" size={14} />
          Reset Semua Pemain
        </button>
      ) : (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn btn-danger" disabled={busy} onClick={doReset}>
            {busy ? <span className="spinner" /> : <Icon name="close" size={14} />}
            Konfirmasi Reset All
          </button>
          <button className="btn btn-ghost" onClick={() => setConfirm(false)}>
            Batal
          </button>
          <span className="error-text" style={{ fontSize: 12 }}>DESTRUKTIF — tidak bisa di-undo!</span>
        </div>
      )}
    </section>
  );
}

function fmtUptime(s: number) {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const parts: string[] = [];
  if (d) parts.push(`${d}h`);
  if (h || d) parts.push(`${h}j`);
  parts.push(`${m}m`);
  return parts.join(" ");
}

function latencyTone(ms: number | null) {
  if (ms === null) return { label: "—", cls: "badge-off" };
  if (ms < 150) return { label: `${ms} ms`, cls: "badge-on" };
  if (ms < 400) return { label: `${ms} ms`, cls: "badge-off" };
  return { label: `${ms} ms`, cls: "badge-off" };
}

function BotStatsView({
  stats,
  loadError,
}: {
  stats: BotStats | null;
  loadError: string | null;
}) {
  if (!stats) {
    return !loadError ? (
      <div className="card card-pad faint">Statistik bot belum tersedia.</div>
    ) : null;
  }

  const lat = latencyTone(stats.latency_ms);
  const g = stats.guild;

  return (
    <div className="stack">
      {/* Status bot */}
      <section className="stat-grid stagger" aria-label="Status bot">
        <div className="stat">
          <div className="stat-label">
            <Icon name="activity" size={16} />
            Status
          </div>
          <div style={{ marginTop: 8 }}>
            <span className={stats.online ? "badge badge-on" : "badge badge-off"}>
              <Icon name="activity" size={13} />
              {stats.online ? "Online" : "Offline"}
            </span>
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">
            <Icon name="signal" size={16} />
            Latency Gateway
          </div>
          <div style={{ marginTop: 8 }}>
            <span className={`badge ${lat.cls}`}>
              <Icon name="signal" size={13} />
              {lat.label}
            </span>
          </div>
        </div>
        <StatCard icon="clock" label="Uptime" value={fmtUptime(stats.uptime_seconds)} />
        <StatCard icon="terminal" label="Prefix" value={stats.prefix} />
      </section>

      {/* Detail guild */}
      {g && (
        <section className="card card-pad">
          <h3 style={{ marginBottom: 16 }}>Detail Server</h3>
          <div className="kv-grid stagger">
            <KV icon="users" label="Total Member" value={nf(g.member_count)} />
            <KV icon="users" label="Manusia" value={g.humans !== null ? nf(g.humans) : "—"} />
            <KV icon="dragon" label="Bot" value={nf(g.bots)} />
            <KV icon="mic" label="Sedang di Voice" value={nf(g.members_in_voice)} />
            <KV icon="trophy" label="Boost" value={`${nf(g.boosts)} (Tier ${g.boost_tier})`} />
            <KV icon="grid" label="Channel Teks" value={nf(g.text_channels)} />
            <KV icon="mic" label="Channel Voice" value={nf(g.voice_channels)} />
            <KV icon="shield" label="Role" value={nf(g.roles)} />
          </div>
        </section>
      )}

      {/* Detail ekonomi */}
      <section className="card card-pad">
        <h3 style={{ marginBottom: 16 }}>Ekonomi &amp; Sistem</h3>
        <div className="kv-grid stagger">
          <KV icon="users" label="Pemain Terdaftar" value={nf(stats.economy.players)} />
          <KV icon="coins" label="Total Koin" value={nf(stats.economy.total_coins)} />
          <KV icon="trophy" label="Rata-rata Level" value={String(stats.economy.average_level)} />
          <KV icon="trophy" label="Level Tertinggi" value={nf(stats.economy.max_level)} />
          <KV icon="activity" label="Total XP" value={nf(stats.economy.total_xp)} />
          <KV icon="vault" label="Kas (Treasury)" value={nf(stats.treasury_balance)} />
          <KV icon="terminal" label="Command Terdaftar" value={nf(stats.commands_registered)} />
          <KV
            icon="megaphone"
            label="Channel Announce Diset"
            value={`${stats.announce_channels_configured} / 7`}
          />
        </div>
      </section>
    </div>
  );
}

function KV({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className="kv">
      <div className="kv-icon" aria-hidden="true">
        <Icon name={icon} size={16} />
      </div>
      <div className="kv-text">
        <div className="kv-label">{label}</div>
        <div className="kv-value tnum">{value}</div>
      </div>
    </div>
  );
}
