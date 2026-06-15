// app/api/admin/announce/route.ts
//
// Proxy aman untuk POST /api/announce (broadcast ke kategori announce).

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

const VALID_CATEGORIES = [
  "market",
  "levelup",
  "birthday",
  "boss",
  "booster",
  "binomo",
  "default",
];

export async function POST(req: Request) {
  // TODO: cek session admin di sini sebelum lanjut.

  let payload: { category?: string; message?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { category, message } = payload;
  if (!category || !VALID_CATEGORIES.includes(category)) {
    return NextResponse.json(
      { error: `category harus salah satu dari: ${VALID_CATEGORIES.join(", ")}` },
      { status: 400 },
    );
  }
  if (!message || !message.trim()) {
    return NextResponse.json({ error: "message kosong" }, { status: 400 });
  }

  try {
    const data = await botPost("/api/announce", { category, message });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
