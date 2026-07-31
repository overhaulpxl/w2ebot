"use client";

import { useState } from "react";
import { phase9bMutation } from "@/lib/phase9bMutations";

export function ControlledAction({ route, label, payload }: { route: string; label: string; payload: Record<string, unknown> }) {
  const [requestId] = useState(() => crypto.randomUUID());
  const [status, setStatus] = useState("");
  return <button onClick={async () => {
    try { await phase9bMutation(route, payload, requestId); setStatus("Selesai"); }
    catch (error) { setStatus(error instanceof Error ? error.message : "internal_error"); }
  }}>{label}{status ? `: ${status}` : ""}</button>;
}
