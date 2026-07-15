"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "./Icon";

interface UserData {
  id: string;
  displayName: string;
  coins: number;
  xp: number;
  level: number;
  xp_to_next: number;
  rank: number | null;
  crypto: Record<string, number>;
  rigs: Record<string, unknown>;
  items: Record<string, number>;
  pet: string | null;
  total_vc_minutes: number;
  married_to: string | null;
  cooldowns: { work: number; rob: number; pray: number; curse: number };
}

function nf(value: number) { return value.toLocaleString("id-ID"); }

export function UserModal({ userId, onClose }: { userId: string; onClose: () => void }) {
  const [user, setUser] = useState<UserData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await fetch(`/api/dashboard/read/user/${userId}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "internal_error");
      setUser(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "internal_error");
    } finally { setLoading(false); }
  }, [userId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="Profil user">
      <div className="modal-content" onClick={(event) => event.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Tutup"><Icon name="close" size={18} /></button>
        {loading && <div className="card-pad"><span className="spinner" /></div>}
        {error && <div className="card-pad error-text">Gagal memuat profil: {error}</div>}
        {user && !loading && (
          <div className="stack">
            <div><h2>{user.displayName}</h2><span className="faint tnum">ID: {user.id}</span></div>
            <div className="stat-grid">
              <MiniStat label="Level" value={nf(user.level)} />
              <MiniStat label="Rank" value={user.rank ? `#${user.rank}` : "-"} />
              <MiniStat label="Koin" value={nf(user.coins)} />
              <MiniStat label="XP" value={`${nf(user.xp)}/${nf(user.xp_to_next)}`} />
            </div>
            <div className="stat-grid">
              <MiniStat label="Crypto" value={String(Object.keys(user.crypto).length)} />
              <MiniStat label="Rig" value={String(Object.keys(user.rigs).length)} />
              <MiniStat label="Item" value={String(Object.keys(user.items).length)} />
              <MiniStat label="VC Menit" value={nf(user.total_vc_minutes)} />
            </div>
            <p className="muted">Profil ini bersifat baca saja. Mutasi admin lama dinonaktifkan oleh Phase 9A.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return <div className="stat"><div className="stat-label">{label}</div><strong className="tnum">{value}</strong></div>;
}
