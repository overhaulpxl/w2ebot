import { EconomyNav } from "@/components/EconomyNav";
import { PanelState } from "@/components/PanelState";
import { MetricTable } from "@/components/MetricTable";
import { requireDashboardSession } from "@/lib/dashboardAuth";
import { internalRequest } from "@/lib/internalRequest";

export default async function Page() {
  const validated = await requireDashboardSession("OPERATOR_AUDIT_READ");
  let data: unknown; let error = "";
  try { data = await internalRequest("/internal/phase9a/audit/list", { limit: 100 }, validated.identity, "OPERATOR_AUDIT_READ"); }
  catch (e) { error = e instanceof Error ? e.message : "internal_error"; }
  return <main className="economy-shell"><header className="economy-header"><h1>Audit Operator</h1></header><EconomyNav />
    <PanelState title="Riwayat" status={error ? "error" : "ready"}>{error ? <p>{error}</p> : <MetricTable value={data} />}</PanelState></main>;
}
