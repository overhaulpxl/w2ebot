import { EconomyReportPage } from "@/components/EconomyReportPage";
import { loadEconomyDashboard } from "@/lib/economyDashboard";

export default async function EconomyPage() {
  try { return <EconomyReportPage title="Ringkasan Economy" report={await loadEconomyDashboard("overview")} />; }
  catch (error) { return <EconomyReportPage title="Ringkasan Economy" error={error instanceof Error ? error.message : "internal_error"} />; }
}
