"use client";

import { useState } from "react";

export function OperatorMarketManagement() {
  const [listingId, setListingId] = useState("");
  const [result, setResult] = useState("");
  
  async function performAction(action: 'cancel_listing') {
    if (!listingId) return setResult("Isi Listing ID!");
    
    setResult("Processing...");
    try {
      const res = await fetch("/api/operator/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, listingId })
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
        <h3>Force Cancel / Takedown Listing</h3>
        <p className="muted">Membatalkan penjualan item secara paksa dan mengembalikan barang ke inventory pemilik.</p>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
          <input type="text" placeholder="Listing ID" value={listingId} onChange={e => setListingId(e.target.value)} style={{ flex: 1 }} />
          <button className="btn btn-danger" onClick={() => performAction("cancel_listing")}>Takedown</button>
        </div>
      </div>
      <p>{result}</p>
    </div>
  );
}