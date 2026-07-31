import { EconomyReportPage } from "@/components/EconomyReportPage";
import { loadEconomyDashboard } from "@/lib/economyDashboard";
export default async function Page() { try { return <EconomyReportPage title="Crypto & Mining" report={await loadEconomyDashboard("crypto-mining")} />; } catch (e) { return <EconomyReportPage title="Crypto & Mining" error={e instanceof Error ? e.message : "internal_error"} />; } }
