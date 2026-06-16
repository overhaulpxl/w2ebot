// components/AuditLog.tsx
//
// Audit log aksi admin. Endpoint /api/audit token-gated, jadi fetch lewat
// Route Handler proxy /api/admin/audit (token disuntik di server).
"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "./Icon";
import type { AuditEntry } from "@/lib/botApi";

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleString("id-ID", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

const ACTION_LABELS: Record<string, string> = {
  coins: "Ubah Koin",
  xp: "Tambah XP",
  "give-item": "Beri Item",
  "reset-cooldown": "Reset Cooldown",
  "boss-spawn": "Spawn Boss",
  announce: "Pengumuman",
  "announce-config": "Set Channel Announce",
};

export function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/admin/audit", { cache: "no-store" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `Gagal (${res.status})`);
      setEntries(data.entries ?? []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="card" aria-labelledby="audit-title">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "16px 16px 0",
        }}
      >
        <h3 id="audit-title">Audit Log Aksi Admin</h3>
        <button className="btn btn-ghost" onClick={load} disabled={loading} aria-label="Muat ulang audit log">
          {loading ? <span className="spinner" /> : <Icon name="refresh" size={16} />}
          Refresh
        </button>
      </div>

      {error && (
        <div className="card-pad error-text" role="alert">
          {error}
        </div>
      )}

      {!error && entries && entries.length === 0 && !loading && (
        <div className="card-pad faint">Belum ada aksi admin yang tercatat.</div>
      )}

      {entries && entries.length > 0 && (
        <table className="lb" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th style={{ width: 140 }}>Waktu</th>
              <th style={{ width: 160 }}>Aksi</th>
              <th>Target</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td className="faint tnum" style={{ fontSize: 13 }}>
                  {fmtTime(e.ts)}
                </td>
                <td>
                  <span className="badge badge-off">{ACTION_LABELS[e.action] ?? e.action}</span>
                </td>
                <td className="tnum" style={{ fontSize: 13 }}>
                  {e.target_id ?? "—"}
                </td>
                <td className="muted" style={{ fontSize: 13 }}>
                  {e.detail ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
