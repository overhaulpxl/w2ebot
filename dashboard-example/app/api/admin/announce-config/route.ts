// app/api/admin/announce-config/route.ts
//
// Proxy aman untuk POST /api/announce-config (set channel pengumuman per kategori).
// Token di server; browser cukup panggil /api/admin/announce-config.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

const KEYS = ["default", "market", "levelup", "birthday", "boss", "booster", "binomo"];

export async function POST(req: Request) {
  // TODO: cek session admin di sini sebelum lanjut.

  let payload: Record<string, unknown>;
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  // Bentuk body: tiap key channel ID (digit) atau "" (fallback).
  const body: Record<string, string> = {};
  for (const k of KEYS) {
    const v = payload[k];
    const s = v == null ? "" : String(v).trim();
    if (s && !/^\d+$/.test(s)) {
      return NextResponse.json({ error: `Channel id tidak valid untuk ${k}` }, { status: 400 });
    }
    body[k] = s;
  }

  try {
    const data = await botPost("/api/announce-config", body);
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
