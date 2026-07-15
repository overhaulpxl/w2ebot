import { EconomyReportPage } from "@/components/EconomyReportPage";
import { loadEconomyDashboard } from "@/lib/economyDashboard";
export default async function Page() { try { return <EconomyReportPage title="Liabilitas" report={await loadEconomyDashboard("liabilities")} />; } catch (e) { return <EconomyReportPage title="Liabilitas" error={e instanceof Error ? e.message : "internal_error"} />; } }
