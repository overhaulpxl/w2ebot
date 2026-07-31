import { NextRequest } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { phase9bWrite } from "@/lib/phase9bApi";
export async function POST(request: NextRequest) { return phase9bWrite(await getDashboardSession("REVIEWED_RECOVERY_CONTROL"), request, "/internal/phase9b/recovery/resolve", "REVIEWED_RECOVERY_CONTROL", ["requestId","targetType","targetId","resolution","expectedVersion","reason"]); }
