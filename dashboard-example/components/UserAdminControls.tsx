// components/UserAdminControls.tsx
//
// Kontrol admin per-user (set koin, beri item, reset cooldown, persona, birthday,
// bg, bounty, reset weekly/quest, paksa cerai) untuk halaman /user/[id].
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
const COOLDOWNS = ["work", "rob", "pray", "curse", "daily", "all"];

export function UserAdminControls({ userId }: { userId: string }) {
  const toast = useToast();
  const [delta, setDelta] = useState("");
  const [xpDelta, setXpDelta] = useState("");
  const [itemId, setItemId] = useState(ITEMS[0]);
  const [cdType, setCdType] = useState(COOLDOWNS[0]);
  const [persona, setPersona] = useState("");
  const [birthday, setBirthday] = useState("");
  const [bgUrl, setBgUrl] = useState("");
  const [bounty, setBounty] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

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
    <section className="card card-pad stack" aria-labelledby="user-admin">
      <h3 id="user-admin">Kontrol Admin</h3>

      <div className="row">
        <div className="field">
          <label className="label" htmlFor="u-delta">
            Ubah Koin (Δ)
          </label>
          <input
            id="u-delta"
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
          <label className="label" htmlFor="u-xp">
            Tambah XP (Δ)
          </label>
          <input
            id="u-xp"
            className="input tnum"
            inputMode="numeric"
            placeholder="cth. 500 atau -100"
            value={xpDelta}
            onChange={(e) => setXpDelta(e.target.value)}
          />
        </div>
        <button
          className="btn btn-primary"
          disabled={busy === "xp"}
          onClick={() => {
            const n = Number(xpDelta);
            if (!Number.isFinite(n) || n === 0) {
              toast("error", "Δ XP harus angka bukan nol.");
              return;
            }
            run("xp", () => callAdmin("/api/admin/xp", { userId, delta: n }), "XP diperbarui.");
          }}
        >
          {busy === "xp" ? <span className="spinner" /> : <Icon name="activity" />}
          Set XP
        </button>
      </div>

      <div className="row">
        <div className="field">
          <label className="label" htmlFor="u-item">
            Item
          </label>
          <select id="u-item" className="select" value={itemId} onChange={(e) => setItemId(e.target.value)}>
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
          onClick={() =>
            run("item", () => callAdmin("/api/admin/give-item", { userId, itemId, qty: 1 }), `Item ${itemId} diberikan.`)
          }
        >
          {busy === "item" ? <span className="spinner" /> : <Icon name="gift" />}
          Beri Item
        </button>
      </div>

      <div className="row">
        <div className="field">
          <label className="label" htmlFor="u-cd">
            Reset Cooldown
          </label>
          <select id="u-cd" className="select" value={cdType} onChange={(e) => setCdType(e.target.value)}>
            {COOLDOWNS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <button
          className="btn btn-ghost"
          disabled={busy === "cd"}
          onClick={() =>
            run("cd", () => callAdmin("/api/admin/reset-cooldown", { userId, type: cdType }), `Cooldown ${cdType} direset.`)
          }
        >
          {busy === "cd" ? <span className="spinner" /> : <Icon name="refresh" />}
          Reset
        </button>
      </div>

      <div className="divider" />

      {/* Set Persona */}
      <div className="row">
        <div className="field" style={{ flex: 1 }}>
          <label className="label" htmlFor="u-persona">
            Set Persona
          </label>
          <textarea
            id="u-persona"
            className="input"
            rows={3}
            placeholder="Persona AI untuk user ini..."
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
          />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <button
            className="btn btn-primary"
            disabled={busy === "persona"}
            onClick={() => {
              if (!persona.trim()) {
                toast("error", "Persona tidak boleh kosong. Gunakan Reset.");
                return;
              }
              run("persona", () => callAdmin("/api/admin/persona", { userId, persona }), "Persona diperbarui.");
            }}
          >
            {busy === "persona" ? <span className="spinner" /> : <Icon name="users" />}
            Set Persona
          </button>
          <button
            className="btn btn-ghost"
            disabled={busy === "persona-reset"}
            onClick={() =>
              run("persona-reset", () => callAdmin("/api/admin/persona", { userId, persona: "" }), "Persona direset.")
            }
          >
            {busy === "persona-reset" ? <span className="spinner" /> : <Icon name="refresh" />}
            Reset Persona
          </button>
        </div>
      </div>

      <div className="divider" />

      {/* Set Birthday */}
      <div className="row">
        <div className="field">
          <label className="label" htmlFor="u-birthday">
            Set Birthday (DD-MM)
          </label>
          <input
            id="u-birthday"
            className="input"
            placeholder="cth. 25-12"
            maxLength={5}
            value={birthday}
            onChange={(e) => setBirthday(e.target.value)}
          />
        </div>
        <button
          className="btn btn-primary"
          disabled={busy === "birthday"}
          onClick={() => {
            run(
              "birthday",
              () => callAdmin("/api/admin/birthday", { userId, date: birthday }),
              birthday ? "Birthday diset." : "Birthday dihapus."
            );
          }}
        >
            {busy === "birthday" ? <span className="spinner" /> : <Icon name="clock" />}
          Set Birthday
        </button>
      </div>

      <div className="divider" />

      {/* Set Background */}
      <div className="row">
        <div className="field" style={{ flex: 1 }}>
          <label className="label" htmlFor="u-bg">
            Set Background URL
          </label>
          <input
            id="u-bg"
            className="input"
            placeholder="https://example.com/bg.png"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
          />
        </div>
        <button
          className="btn btn-primary"
          disabled={busy === "bg"}
          onClick={() => {
            run(
              "bg",
              () => callAdmin("/api/admin/bg", { userId, url: bgUrl }),
              bgUrl ? "Background diset." : "Background dihapus."
            );
          }}
        >
          {busy === "bg" ? <span className="spinner" /> : <Icon name="grid" />}
          Set BG
        </button>
      </div>

      <div className="divider" />

      {/* Bounty */}
      <div className="row">
        <div className="field">
          <label className="label" htmlFor="u-bounty">
            Bounty (0 = hapus)
          </label>
          <input
            id="u-bounty"
            className="input tnum"
            inputMode="numeric"
            placeholder="cth. 10000"
            value={bounty}
            onChange={(e) => setBounty(e.target.value)}
          />
        </div>
        <button
          className="btn btn-primary"
          disabled={busy === "bounty"}
          onClick={() => {
            const n = Number(bounty);
            if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) {
              toast("error", "Bounty harus integer >= 0.");
              return;
            }
            run("bounty", () => callAdmin("/api/admin/bounty", { userId, amount: n }), n === 0 ? "Bounty dihapus." : "Bounty diset.");
          }}
        >
          {busy === "bounty" ? <span className="spinner" /> : <Icon name="activity" />}
          Set Bounty
        </button>
      </div>

      <div className="divider" />

      {/* Reset Weekly & Reset Quest */}
      <div className="row">
        <button
          className="btn btn-ghost"
          disabled={busy === "reset-weekly"}
          onClick={() =>
            run("reset-weekly", () => callAdmin("/api/admin/reset-weekly", { userId }), "Weekly direset.")
          }
        >
          {busy === "reset-weekly" ? <span className="spinner" /> : <Icon name="refresh" />}
          Reset Weekly
        </button>
        <button
          className="btn btn-ghost"
          disabled={busy === "reset-quest"}
          onClick={() =>
            run("reset-quest", () => callAdmin("/api/admin/reset-quest", { userId }), "Quest direset.")
          }
        >
          {busy === "reset-quest" ? <span className="spinner" /> : <Icon name="refresh" />}
          Reset Quest
        </button>
      </div>

      <div className="divider" />

      {/* Paksa Cerai */}
      <div className="row">
        <button
          className="btn btn-danger"
          disabled={busy === "divorce"}
          onClick={() =>
            run("divorce", () => callAdmin("/api/admin/divorce", { userId }), "Paksa cerai berhasil.")
          }
        >
          {busy === "divorce" ? <span className="spinner" /> : <Icon name="close" />}
          Paksa Cerai
        </button>
      </div>
    </section>
  );
}
