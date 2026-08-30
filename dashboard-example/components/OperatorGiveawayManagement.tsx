"use client";

import { useState } from "react";

export function OperatorGiveawayManagement() {
  const [giveawayId, setGiveawayId] = useState("");
  const [result, setResult] = useState("");
  
  async function performAction() {
    if (!giveawayId) return setResult("Isi Giveaway ID!");
    
    setResult("Processing refund...");
    try {
      const res = await fetch("/api/operator/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "cancel_giveaway", giveawayId })
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
      <div className="card card-pad" style={{ marginBottom: 15 }}>
        <h3>Force Cancel / Refund Giveaway</h3>
        <p className="muted">Membatalkan giveaway yang sedang berlangsung dan mengembalikan semua aset ke kas/sistem secara aman.</p>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
          <input type="text" placeholder="Giveaway ID" value={giveawayId} onChange={e => setGiveawayId(e.target.value)} style={{ flex: 1 }} />
          <button className="btn btn-danger" onClick={performAction}>Refund All</button>
        </div>
      </div>
      <p>{result}</p>
    </div>
  );
}