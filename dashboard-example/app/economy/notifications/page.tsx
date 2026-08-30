import { EconomyNav } from "@/components/EconomyNav";
import { PanelState } from "@/components/PanelState";
import { RouteEditor } from "@/components/RouteEditor";
import { loadEconomyDashboard } from "@/lib/economyDashboard";
import { internalRequest } from "@/lib/internalRequest";
import { getDashboardSession } from "@/lib/dashboardAuth";

export default async function Page() {
  let routes: any[] = []; let channels: any[] = []; let error = "";
  try { 
    routes = (await loadEconomyDashboard<any>("notifications")).routes ?? []; 
    const session = await getDashboardSession("DASHBOARD_VIEW");
    if (session) {
      const res = await internalRequest<any>("/internal/phase9c/discord/channels", {}, session.identity as unknown as Record<string, unknown>);
      channels = res.channels || [];
    }
  }
  catch (e) { error = e instanceof Error ? e.message : "internal_error"; }
  return <main className="economy-shell"><header className="economy-header"><h1>Routing Notifikasi</h1></header><EconomyNav />
    <PanelState title="Rute" status={error ? "error" : routes.length ? "ready" : "empty"}>
      {error ? <p>{error}</p> : <div className="route-list">{routes.map(route => <RouteEditor key={route.category} route={route} channels={channels} />)}</div>}
    </PanelState></main>;
}
