"use client";

import { useState } from "react";

export function OperatorUserManagement() {
  const [userId, setUserId] = useState("");
  const [currency, setCurrency] = useState("ECY");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [result, setResult] = useState("");
  
  async function performAction(action: 'mint' | 'remove' | 'wipe') {
    if (!userId) return setResult("Isi User ID dulu!");
    if ((action === 'mint' || action === 'remove') && (!amount || !reason)) {
      return setResult("Isi nominal dan alasan!");
    }
    const confirmMsg = action === 'wipe' 
      ? `YAKIN ingin MENGHAPUS BERSIH data user ${userId}?`
      : `Yakin ingin ${action} ${amount} ${currency} untuk user ${userId}?`;
    if (!confirm(confirmMsg)) return;

    setResult("Processing...");
    try {
      const res = await fetch("/api/operator/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, userId, currency, amount: parseInt(amount), reason })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Gagal");
      setResult(`Sukses: ${JSON.stringify(data)}`);
    } catch (e: any) {
      setResult(`Error: ${e.message}`);
    }
  }

  return (
    <div className="operator-panel">
      <div style={{ marginBottom: 15 }}>
        <label>User ID (Discord):</label>
        <input type="text" value={userId} onChange={e => setUserId(e.target.value)} placeholder="Contoh: 1234567890" />
      </div>
      
      <div className="card card-pad" style={{ marginBottom: 15, background: "#111" }}>
        <h3>Mutasi Keuangan</h3>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
          <select value={currency} onChange={e => setCurrency(e.target.value)}>
            <option value="ECY">ECY (Koin)</option>
            <option value="ETM">ETM (Premium)</option>
          </select>
          <input type="number" placeholder="Nominal" value={amount} onChange={e => setAmount(e.target.value)} />
        </div>
        <input style={{ width: "100%", marginBottom: 10 }} type="text" placeholder="Alasan / Bukti" value={reason} onChange={e => setReason(e.target.value)} />
        <div style={{ display: "flex", gap: 10 }}>
          <button className="btn btn-primary" onClick={() => performAction("mint")}>Inject (Mint)</button>
          <button className="btn btn-danger" onClick={() => performAction("remove")}>Tarik (Confiscate)</button>
        </div>
      </div>

      <div className="card card-pad" style={{ marginBottom: 15, background: "#311" }}>
        <h3 style={{ color: "#f55" }}>Hapus Data (Wipe)</h3>
        <p className="muted">Tombol ini akan menghapus semua data dompet, RPG, Crypto, dan Mining milik player tersebut secara permanen. Tidak bisa di-undo.</p>
        <button className="btn btn-danger" onClick={() => performAction("wipe")}>Wipe Player Data</button>
      </div>

      <p>{result}</p>
    </div>
  );
}