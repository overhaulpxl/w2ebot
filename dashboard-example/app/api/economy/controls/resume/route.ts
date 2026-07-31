import { NextRequest } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { phase9bWrite } from "@/lib/phase9bApi";
export async function POST(request: NextRequest) { return phase9bWrite(await getDashboardSession("ECONOMY_PAUSE_CONTROL"), request, "/internal/phase9b/features/resume", "ECONOMY_PAUSE_CONTROL", ["requestId","feature","reason","expectedVersion"]); }
