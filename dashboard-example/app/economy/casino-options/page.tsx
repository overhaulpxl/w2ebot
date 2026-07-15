import { EconomyReportPage } from "@/components/EconomyReportPage";
import { loadEconomyDashboard } from "@/lib/economyDashboard";
export default async function Page() { try { return <EconomyReportPage title="Casino & Eternal Options" report={await loadEconomyDashboard("casino-options")} />; } catch (e) { return <EconomyReportPage title="Casino & Eternal Options" error={e instanceof Error ? e.message : "internal_error"} />; } }
