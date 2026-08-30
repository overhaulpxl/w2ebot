import { NextResponse } from "next/server";
import { internalFetch } from "@/lib/internal-fetch";
import { verifySession } from "@/lib/auth";

export async function GET() {
  const session = await verifySession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const data = await internalFetch("/internal/phase9c/discord/channels", {});
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("Failed to fetch discord channels:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch channels" },
      { status: error.status || 500 }
    );
  }
}
