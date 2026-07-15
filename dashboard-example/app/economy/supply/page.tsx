import { EconomyReportPage } from "@/components/EconomyReportPage";
import { loadEconomyDashboard } from "@/lib/economyDashboard";
export default async function Page() { try { return <EconomyReportPage title="Supply & Distribusi" report={await loadEconomyDashboard("supply")} />; } catch (e) { return <EconomyReportPage title="Supply & Distribusi" error={e instanceof Error ? e.message : "internal_error"} />; } }
