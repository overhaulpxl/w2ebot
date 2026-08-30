"use client";

import { useState } from "react";

export function OperatorCryptoManagement() {
  const [result, setResult] = useState("");
  
  async function performAction() {
    setResult("Processing tick...");
    try {
      const res = await fetch("/api/operator/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "crypto_tick" })
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
        <h3>Force Market Tick</h3>
        <p className="muted">Memaksa pergerakan harga Crypto (Market Tick) sekarang juga, mengabaikan jadwal cron.</p>
        <button className="btn btn-primary" onClick={performAction}>Simulate Market Tick Now</button>
      </div>
      <p>{result}</p>
    </div>
  );
}