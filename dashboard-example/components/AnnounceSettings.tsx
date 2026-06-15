// components/AnnounceSettings.tsx
//
// Form pengaturan channel pengumuman per kategori. Tiap kategori pilih channel
// (atau "auto / fallback"). Simpan lewat Route Handler /api/admin/announce-config.
"use client";

import { useState } from "react";
import { Icon } from "./Icon";
import { useToast } from "./Toast";
import {
  ANNOUNCE_CATEGORIES,
  ANNOUNCE_LABELS,
  type Channel,
  type AnnounceConfig,
} from "@/lib/botApi";

export function AnnounceSettings({
  channels,
  config,
}: {
  channels: Channel[];
  config: AnnounceConfig | null;
}) {
  const toast = useToast();
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const k of ANNOUNCE_CATEGORIES) init[k] = config?.[k] ?? "";
    return init;
  });
  const [busy, setBusy] = useState(false);

  if (!config) {
    return <div className="card card-pad faint">Konfigurasi pengumuman belum tersedia.</div>;
  }

  function setOne(key: string, val: string) {
    setValues((v) => ({ ...v, [key]: val }));
  }

  async function save() {
    setBusy(true);
    try {
      const res = await fetch("/api/admin/announce-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `Gagal (${res.status})`);
      toast("success", "Pengaturan pengumuman tersimpan.");
    } catch (e: any) {
      toast("error", e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card card-pad stack" aria-labelledby="announce-config">
      <div>
        <h3 id="announce-config">Channel Pengumuman</h3>
        <p className="helper" style={{ marginTop: 4 }}>
          Pilih channel tujuan tiap kategori. Kosongkan (Auto) agar pakai fallback: kategori →
          default → channel <code>general</code>/<code>chat</code>.
        </p>
      </div>

      <div className="announce-grid">
        {ANNOUNCE_CATEGORIES.map((cat) => (
          <div className="field" key={cat}>
            <label className="label" htmlFor={`ann-${cat}`}>
              {ANNOUNCE_LABELS[cat] ?? cat}
            </label>
            <select
              id={`ann-${cat}`}
              className="select"
              value={values[cat]}
              onChange={(e) => setOne(cat, e.target.value)}
            >
              <option value="">Auto / fallback</option>
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.name}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      <div>
        <button className="btn btn-primary" onClick={save} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="megaphone" />}
          Simpan Pengaturan
        </button>
      </div>
    </section>
  );
}
