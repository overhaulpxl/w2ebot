// components/AdminPanel.tsx
//
// Client component: SEMUA aksi write memanggil Route Handler Next.js sendiri
// (/api/admin/*), BUKAN bot API langsung. Token tidak pernah ada di browser.
//
// UX: tiap aksi punya loading + disabled state, validasi inline, dan feedback toast.
"use client";

import { useState } from "react";
import { Icon } from "./Icon";
import { useToast } from "./Toast";

async function callAdmin(path: string, body: unknown) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Gagal (${res.status})`);
  return data;
}

const ITEMS = ["shield", "double_xp", "lucky_charm"];

export function AdminPanel({ only }: { only?: "user" | "server" }) {
  const toast = useToast();

  // state per-form
  const [userId, setUserId] = useState("");
  const [userIdError, setUserIdError] = useState<string | null>(null);
  const [delta, setDelta] = useState("");
  const [itemId, setItemId] = useState(ITEMS[0]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  function validUser() {
    if (!/^\d+$/.test(userId)) {
      setUserIdError("User ID harus berupa angka (Discord ID).");
      return false;
    }
    setUserIdError(null);
    return true;
  }

  async function run(key: string, fn: () => Promise<any>, okMsg: string) {
    setBusy(key);
    try {
      await fn();
      toast("success", okMsg);
    } catch (e: any) {
      toast("error", e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="admin-grid stagger">
      {/* Kartu: aksi berbasis user */}
      {only !== "server" && (
      <section className="card card-pad stack" aria-labelledby="user-actions">
        <h3 id="user-actions">Aksi Pemain</h3>

        <div className="field">
          <label className="label" htmlFor="uid">
            User ID (Discord)
          </label>
          <input
            id="uid"
            className="input tnum"
            inputMode="numeric"
            placeholder="cth. 123456789012345678"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            onBlur={validUser}
            aria-invalid={userIdError ? "true" : undefined}
            aria-describedby="uid-help"
          />
          {userIdError ? (
            <span className="error-text" role="alert">
              {userIdError}
            </span>
          ) : (
            <span id="uid-help" className="helper">
              Dipakai untuk semua aksi di kartu ini.
            </span>
          )}
        </div>

        <div className="row">
          <div className="field">
            <label className="label" htmlFor="delta">
              Ubah Koin (Δ)
            </label>
            <input
              id="delta"
              className="input tnum"
              inputMode="numeric"
              placeholder="cth. 5000 atau -2000"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
            />
          </div>
          <button
            className="btn btn-primary"
            disabled={busy === "coins"}
            onClick={() => {
              if (!validUser()) return;
              const n = Number(delta);
              if (!Number.isFinite(n) || n === 0) {
                toast("error", "Δ koin harus angka bukan nol.");
                return;
              }
              run("coins", () => callAdmin("/api/admin/coins", { userId, delta: n }), "Koin diperbarui.");
            }}
          >
            {busy === "coins" ? <span className="spinner" /> : <Icon name="coins" />}
            Set Koin
          </button>
        </div>

        <div className="row">
          <div className="field">
            <label className="label" htmlFor="item">
              Item
            </label>
            <select id="item" className="select" value={itemId} onChange={(e) => setItemId(e.target.value)}>
              {ITEMS.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn btn-ghost"
            disabled={busy === "item"}
            onClick={() => {
              if (!validUser()) return;
              run("item", () => callAdmin("/api/admin/give-item", { userId, itemId, qty: 1 }), `Item ${itemId} diberikan.`);
            }}
          >
            {busy === "item" ? <span className="spinner" /> : <Icon name="gift" />}
            Beri Item
          </button>
        </div>
      </section>
      )}

      {/* Kartu: aksi server */}
      {only !== "user" && (
      <section className="card card-pad stack" aria-labelledby="server-actions">
        <h3 id="server-actions">Aksi Server</h3>

        <div className="field">
          <label className="label" htmlFor="announce">
            Pesan Pengumuman (kategori market)
          </label>
          <input
            id="announce"
            className="input"
            placeholder="Tulis pengumuman…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <span className="helper">Dikirim bot ke channel kategori market.</span>
        </div>
        <button
          className="btn btn-primary"
          disabled={busy === "announce"}
          onClick={() => {
            if (!message.trim()) {
              toast("error", "Pesan tidak boleh kosong.");
              return;
            }
            run(
              "announce",
              () => callAdmin("/api/admin/announce", { category: "market", message }),
              "Pengumuman terkirim.",
            ).then(() => setMessage(""));
          }}
        >
          {busy === "announce" ? <span className="spinner" /> : <Icon name="megaphone" />}
          Kirim Announce
        </button>

        <div className="divider" />

        <button
          className="btn btn-danger"
          disabled={busy === "boss"}
          onClick={() =>
            run("boss", () => callAdmin("/api/admin/boss-spawn", {}), "Boss raid di-spawn.")
          }
        >
          {busy === "boss" ? <span className="spinner" /> : <Icon name="dragon" />}
          Spawn Boss Raid
        </button>
        <span className="helper">Akan gagal (409) kalau sudah ada boss aktif.</span>
      </section>
      )}
    </div>
  );
}
