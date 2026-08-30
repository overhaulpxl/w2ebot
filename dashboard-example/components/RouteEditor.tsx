"use client";

import { useState } from "react";
import { phase9bMutation } from "@/lib/phase9bMutations";

export function RouteEditor({ route, channels = [] }: { route: any, channels?: any[] }) {
  const [channelId, setChannelId] = useState(route.channelId ?? "");
  const [result, setResult] = useState("");
  async function save() {
    try {
      await phase9bMutation(`/api/economy/notifications/routes/${route.category}`, {
        enabled: true, channelId, roleMentionId: route.roleMentionId ?? null,
        eventTypes: route.eventTypes ?? [], expectedVersion: Number(route.version ?? 0),
      }, crypto.randomUUID());
      setResult("Tersimpan");
    } catch (error) { setResult(error instanceof Error ? error.message : "internal_error"); }
  }
  return <div className="route-row">
    <strong>{route.category}</strong>
    <select aria-label={`Channel ${route.category}`} value={channelId} onChange={e => setChannelId(e.target.value)}>
      <option value="">-- Pilih Channel --</option>
      {channels.map(ch => <option key={ch.id} value={ch.id}>{ch.name}</option>)}
    </select>
    <button onClick={save}>Simpan</button>
    <span>{result}</span>
  </div>;
}
