// components/UserModal.tsx
//
// Modal popup profil user. Fetch data dari bot API langsung (read, terbuka),
// tampilkan profil + stats + kontrol admin. Ditampilkan di atas dashboard
// tanpa pindah halaman.
"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "./Icon";
import { useToast } from "./Toast";
import { UserAdminControls } from "./UserAdminControls";

interface UserData {
  id: string;
  displayName: string;
  coins: number;
  xp: number;
  level: number;
  xp_to_next: number;
  rank: number | null;
  crypto: Record<string, number>;
  rigs: Record<string, any>;
  items: Record<string, number>;
  pet: string | null;
  achievements: string[];
  total_vc_minutes: number;
  married_to: string | null;
  children: string[];
  cooldowns: { work: number; rob: number; pray: number; curse: number };
  games?: Record<string, { plays: number; wins: number; losses: number }>;
  top_games?: { game: string; plays: number; wins: number; win_rate: number }[];
  persona?: string | null;
  birthday?: string | null;
  bounty?: number;
  bg_url?: string | null;
}

function nf(n: number) {
  return n.toLocaleString("id-ID");
}

function fmtCooldown(sec: number) {
  if (sec <= 0) return "Siap";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h) return `${h}j ${m}m`;
  return `${m}m`;
}

export function UserModal({
  userId,
  onClose,
}: {
  userId: string;
  onClose: () => void;
}) {
  const [user, setUser] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = process.env.NEXT_PUBLIC_BOT_API_URL || "http://localhost:8081";
      const res = await fetch(`${url}/api/user/${userId}`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `Error ${res.status}`);
      setUser(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  // Flatten rigs (handle both formats)
  const rigRows: [string, number][] = [];
  if (user) {
    for (const [key, val] of Object.entries(user.rigs)) {
      if (typeof val === "object" && val !== null) {
        for (const [tier, count] of Object.entries(val as Record<string, number>)) {
          rigRows.push([`${key} T${tier}`, count]);
        }
      } else {
        rigRows.push([`T${key}`, val as number]);
      }
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="Profil user">
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Tutup">
          <Icon name="close" size={18} />
        </button>

        {loading && (
          <div style={{ display: "grid", placeItems: "center", minHeight: 200 }}>
            <span className="spinner" style={{ width: 28, height: 28 }} />
          </div>
        )}

        {error && (
          <div className="error-text" style={{ padding: 16 }}>
            Gagal memuat profil: {error}
            <br />
            <button className="btn btn-ghost" style={{ marginTop: 12 }} onClick={load}>
              <Icon name="refresh" size={14} /> Coba lagi
            </button>
          </div>
        )}

        {user && !loading && (
          <div className="stack">
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <span className="brand-mark" style={{ width: 52, height: 52, fontSize: 20 }} aria-hidden="true">
                {user.displayName.charAt(0).toUpperCase()}
              </span>
              <div>
                <h2 style={{ margin: 0, fontSize: 20 }}>{user.displayName}</h2>
                <span className="faint tnum" style={{ fontSize: 12 }}>ID: {user.id}</span>
              </div>
            </div>

            {/* Stats row */}
            <div className="stat-grid stagger" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <MiniStat label="Level" value={nf(user.level)} />
              <MiniStat label="Rank" value={user.rank ? `#${user.rank}` : "—"} />
              <MiniStat label="Koin" value={nf(user.coins)} />
              <MiniStat label="XP" value={`${nf(user.xp)}/${nf(user.xp_to_next)}`} />
            </div>

            {/* Top 3 Minigame */}
            {user.top_games && user.top_games.length > 0 && (
              <div>
                <h3 style={{ fontSize: 14, marginBottom: 8 }}>Top Minigame</h3>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {user.top_games.map((g) => (
                    <span key={g.game} className="badge badge-off" style={{ fontSize: 12 }}>
                      {g.game} — {g.plays}x ({g.win_rate}%)
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Assets grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
              <AssetList title="Crypto" entries={Object.entries(user.crypto).map(([k, v]) => `${k}: ${typeof v === "number" && v < 1 ? v.toFixed(4) : v}`)} />
              <AssetList title="Rigs" entries={rigRows.map(([k, v]) => `${k}: ${v}`)} />
              <AssetList title="Items" entries={Object.entries(user.items).map(([k, v]) => `${k}: ${v}`)} />
            </div>

            {/* Status */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 13 }}>
              <StatusRow label="Pet" value={user.pet || "—"} />
              <StatusRow label="VC Minutes" value={nf(user.total_vc_minutes)} />
              <StatusRow label="Nikah" value={user.married_to || "—"} />
              <StatusRow label="Bounty" value={user.bounty ? nf(user.bounty) : "—"} />
              <StatusRow label="CD Work" value={fmtCooldown(user.cooldowns.work)} />
              <StatusRow label="CD Rob" value={fmtCooldown(user.cooldowns.rob)} />
              <StatusRow label="CD Pray" value={fmtCooldown(user.cooldowns.pray)} />
              <StatusRow label="CD Curse" value={fmtCooldown(user.cooldowns.curse)} />
            </div>

            {/* Admin controls — expandable with animation */}
            <ExpandSection title="Kontrol Admin">
              <UserAdminControls userId={user.id} />
            </ExpandSection>

            <ExpandSection title="Reset Player">
              <ResetPlayerSection userId={user.id} />
            </ExpandSection>
          </div>
        )}
      </div>
    </div>
  );
}

function ExpandSection({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 8 }}>
      <button
        className="btn btn-ghost"
        style={{ width: "100%", justifyContent: "space-between" }}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span style={{ fontWeight: 600, fontSize: 14 }}>{title}</span>
        <Icon name={open ? "close" : "grid"} size={14} />
      </button>
      <div className={`expand-body ${open ? "expand-open" : ""}`}>
        <div className="expand-inner">
          {children}
        </div>
      </div>
    </div>
  );
}

const RESET_TARGETS = [
  { id: "coins", label: "Koin (reset ke 0)" },
  { id: "xp", label: "XP & Level (reset ke level 1)" },
  { id: "items", label: "Items (inventory)" },
  { id: "crypto", label: "Crypto (holdings)" },
  { id: "rigs", label: "Mining Rigs" },
  { id: "pet", label: "Pet" },
  { id: "achievements", label: "Achievements" },
  { id: "games", label: "Statistik Minigame" },
  { id: "marriage", label: "Pernikahan (cerai)" },
  { id: "bounty", label: "Bounty" },
  { id: "persona", label: "Persona AI" },
  { id: "birthday", label: "Birthday" },
  { id: "bg", label: "Background Profil" },
  { id: "weekly", label: "Klaim Weekly" },
  { id: "quest", label: "Progress Quest" },
  { id: "cooldowns", label: "Semua Cooldown" },
];

function ResetPlayerSection({ userId }: { userId: string }) {
  const toast = useToast();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setConfirm(false);
  }

  function selectAll() {
    setSelected(new Set(RESET_TARGETS.map((t) => t.id)));
    setConfirm(false);
  }

  function selectNone() {
    setSelected(new Set());
    setConfirm(false);
  }

  async function doReset() {
    if (selected.size === 0) {
      toast("error", "Pilih minimal 1 target reset.");
      return;
    }
    setBusy(true);
    try {
      const targets = selected.size === RESET_TARGETS.length ? ["all"] : Array.from(selected);
      const res = await fetch("/api/admin/reset-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId, targets }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `Gagal (${res.status})`);
      toast("success", `Reset berhasil: ${(data.reset || []).join(", ")}`);
      setSelected(new Set());
      setConfirm(false);
    } catch (e: any) {
      toast("error", e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-ghost" style={{ fontSize: 12, height: 32, padding: "0 10px" }} onClick={selectAll}>
          Pilih Semua
        </button>
        <button className="btn btn-ghost" style={{ fontSize: 12, height: 32, padding: "0 10px" }} onClick={selectNone}>
          Hapus Pilihan
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
        {RESET_TARGETS.map((t) => (
          <label key={t.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={selected.has(t.id)}
              onChange={() => toggle(t.id)}
              style={{ accentColor: "var(--danger)" }}
            />
            {t.label}
          </label>
        ))}
      </div>
      {!confirm ? (
        <button
          className="btn btn-danger"
          disabled={selected.size === 0}
          onClick={() => setConfirm(true)}
        >
          <Icon name="close" size={14} />
          Reset ({selected.size} target)
        </button>
      ) : (
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn btn-danger" disabled={busy} onClick={doReset}>
            {busy ? <span className="spinner" /> : <Icon name="close" size={14} />}
            Konfirmasi Reset
          </button>
          <button className="btn btn-ghost" onClick={() => setConfirm(false)}>
            Batal
          </button>
          <span className="error-text" style={{ fontSize: 12 }}>Tidak bisa di-undo!</span>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div className="faint" style={{ fontSize: 11 }}>{label}</div>
      <div className="tnum" style={{ fontSize: 18, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function AssetList({ title, entries }: { title: string; entries: string[] }) {
  return (
    <div>
      <div className="faint" style={{ fontSize: 11, marginBottom: 4 }}>{title}</div>
      {entries.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--text-faint)" }}>—</div>
      ) : (
        entries.map((e, i) => (
          <div key={i} className="tnum" style={{ fontSize: 12 }}>{e}</div>
        ))
      )}
    </div>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--glass-border)" }}>
      <span className="faint">{label}</span>
      <span className="tnum">{value}</span>
    </div>
  );
}
