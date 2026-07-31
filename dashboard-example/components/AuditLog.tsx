"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "./Icon";
import type { AuditEntry } from "@/lib/botApi";

export function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await fetch("/api/admin/audit", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "internal_error");
      setEntries(data.entries ?? []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "internal_error");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return (
    <section className="card">
      <div className="card-pad" style={{ display: "flex", justifyContent: "space-between" }}>
        <h3>Audit Operator Phase 9A</h3>
        <button className="btn btn-ghost" onClick={() => void load()} disabled={loading}>
          <Icon name="refresh" size={16} /> Muat Ulang
        </button>
      </div>
      {error && <div className="card-pad error-text">{error}</div>}
      {!error && !loading && entries.length === 0 && <div className="card-pad faint">Belum ada operasi terkontrol.</div>}
      {entries.length > 0 && (
        <table className="lb"><thead><tr><th>Waktu</th><th>Operasi</th><th>Target</th><th>Eksekutor</th></tr></thead>
          <tbody>{entries.map((entry) => <tr key={entry.auditId}>
            <td className="tnum">{new Date(entry.createdAt).toLocaleString("id-ID")}</td>
            <td><span className="badge badge-off">{entry.operationType}</span></td>
            <td className="tnum">{entry.targetId}</td><td className="tnum">{entry.executorUserId}</td>
          </tr>)}</tbody></table>
      )}
    </section>
  );
}
