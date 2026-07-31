import { EconomyReportPage } from "@/components/EconomyReportPage";
import { loadEconomyDashboard } from "@/lib/economyDashboard";
export default async function Page() { try { return <EconomyReportPage title="Giveaway" report={await loadEconomyDashboard("giveaway")} />; } catch (e) { return <EconomyReportPage title="Giveaway" error={e instanceof Error ? e.message : "internal_error"} />; } }
