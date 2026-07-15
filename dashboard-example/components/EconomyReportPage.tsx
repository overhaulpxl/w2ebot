import { EconomyNav } from "./EconomyNav";
import { HealthBadge } from "./HealthBadge";
import { MetricTable } from "./MetricTable";
import { PanelState } from "./PanelState";

export function EconomyReportPage({ title, report, error }: { title: string; report?: any; error?: string }) {
  const freshness = report?.freshness ?? (error ? "UNAVAILABLE" : "FRESH");
  const health = report?.data?.health;
  return <main className="economy-shell">
    <header className="economy-header"><div><p className="eyebrow">W2E OPERATIONS</p><h1>{title}</h1></div>{health && <HealthBadge health={health} />}</header>
    <EconomyNav />
    <PanelState title={title} status={error ? "error" : freshness === "STALE" ? "stale" : freshness === "UNAVAILABLE" ? "unavailable" : "ready"}>
      {error ? <p className="error-text">{error}</p> : <><MetricTable value={report?.data ?? report} />
        {report?.warnings?.length > 0 && <ul>{report.warnings.map((warning: string) => <li key={warning}>{warning}</li>)}</ul>}</>}
    </PanelState>
  </main>;
}
