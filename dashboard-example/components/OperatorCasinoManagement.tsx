"use client";

import { useState } from "react";

export function OperatorCasinoManagement() {
  const [sessionId, setSessionId] = useState("");
  const [result, setResult] = useState("");
  
  async function performAction(action: 'terminate_casino') {
    if (!sessionId) return setResult("Isi Session ID!");
    
    setResult("Processing...");
    try {
      const res = await fetch("/api/operator/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, sessionId })
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
        <h3>Terminate Casino Session</h3>
        <p className="muted">Mematikan sesi Blackjack atau Slots yang stuck dan mengembalikan uang taruhan ke dompet pemain.</p>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
          <input type="text" placeholder="Session ID" value={sessionId} onChange={e => setSessionId(e.target.value)} style={{ flex: 1 }} />
          <button className="btn btn-danger" onClick={() => performAction("terminate_casino")}>Kill & Refund</button>
        </div>
      </div>
      <p>{result}</p>
    </div>
  );
}