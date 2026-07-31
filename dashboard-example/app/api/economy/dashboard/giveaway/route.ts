import { getDashboardSession } from "@/lib/dashboardAuth";
import { phase9bRead } from "@/lib/phase9bApi";
export async function GET() { return phase9bRead(await getDashboardSession(), "/internal/phase9b/dashboard/giveaway"); }
