import { EconomyReportPage } from "@/components/EconomyReportPage";
import { loadEconomyDashboard } from "@/lib/economyDashboard";
export default async function Page() { try { return <EconomyReportPage title="Recovery & Outbox" report={await loadEconomyDashboard("recovery", { limit: 100 })} />; } catch (e) { return <EconomyReportPage title="Recovery & Outbox" error={e instanceof Error ? e.message : "internal_error"} />; } }
