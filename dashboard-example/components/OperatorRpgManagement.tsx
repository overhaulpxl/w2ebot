"use client";

import { useState } from "react";

export function OperatorRpgManagement() {
  const [tier, setTier] = useState("NORMAL");
  const [userId, setUserId] = useState("");
  const [itemId, setItemId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [result, setResult] = useState("");
  
  async function performAction(action: 'spawn_boss' | 'grant_item') {
    if (action === 'spawn_boss' && !tier) return setResult("Pilih tier bos!");
    if (action === 'grant_item' && (!userId || !itemId || !quantity)) return setResult("Isi User ID, Item ID, dan jumlah!");
    
    setResult("Processing...");
    try {
      const payload: any = { action };
      if (action === 'spawn_boss') payload.tier = tier;
      if (action === 'grant_item') {
        payload.userId = userId;
        payload.itemId = itemId;
        payload.quantity = parseInt(quantity);
      }
      
      const res = await fetch("/api/operator/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
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
        <h3>Force Spawn Boss</h3>
        <p className="muted">Memaksa boss muncul sekarang juga (membypass jadwal).</p>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
          <select value={tier} onChange={e => setTier(e.target.value)}>
            <option value="NORMAL">Normal Boss</option>
            <option value="ELITE">Elite Boss</option>
            <option value="WORLD">World Boss</option>
          </select>
          <button className="btn btn-primary" onClick={() => performAction("spawn_boss")}>Spawn Boss</button>
        </div>
      </div>

      <div className="card card-pad" style={{ marginBottom: 15 }}>
        <h3>Force Grant Item</h3>
        <p className="muted">Menyuntikkan item langsung ke tas/inventory pemain.</p>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
          <input type="text" placeholder="User ID" value={userId} onChange={e => setUserId(e.target.value)} />
          <input type="text" placeholder="Item ID (contoh: eq_rust_sword)" value={itemId} onChange={e => setItemId(e.target.value)} />
          <input type="number" placeholder="Jumlah" value={quantity} onChange={e => setQuantity(e.target.value)} style={{ width: 80 }} />
          <button className="btn btn-primary" onClick={() => performAction("grant_item")}>Kirim Item</button>
        </div>
      </div>

      <p>{result}</p>
    </div>
  );
}