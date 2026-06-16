// app/api/admin/reset-player/route.ts
//
// Proxy aman untuk POST /api/user/{id}/reset (reset player parsial/full).

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

const VALID_TARGETS = [
  "coins", "xp", "items", "crypto", "rigs", "pet", "achievements",
  "games", "marriage", "bounty", "persona", "birthday", "bg",
  "weekly", "quest", "cooldowns", "all",
];

export async function POST(req: Request) {
  // TODO: cek session admin di sini sebelum lanjut.
  let payload: { userId?: string; targets?: string[] };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { userId, targets = ["all"] } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }
  const invalid = targets.filter((t) => !VALID_TARGETS.includes(t));
  if (invalid.length > 0) {
    return NextResponse.json({ error: `target tidak valid: ${invalid.join(", ")}` }, { status: 400 });
  }
  try {
    const data = await botPost(`/api/user/${userId}/reset`, { targets });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
