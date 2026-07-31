import { EconomyReportPage } from "@/components/EconomyReportPage";
import { loadEconomyDashboard } from "@/lib/economyDashboard";
export default async function Page() { try { return <EconomyReportPage title="Marketplace" report={await loadEconomyDashboard("marketplace")} />; } catch (e) { return <EconomyReportPage title="Marketplace" error={e instanceof Error ? e.message : "internal_error"} />; } }
