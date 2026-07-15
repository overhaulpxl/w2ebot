export function PanelState({ title, status, children }: {
  title: string;
  status: "loading" | "ready" | "empty" | "stale" | "forbidden" | "unavailable" | "error";
  children?: React.ReactNode;
}) {
  return <section className="ops-panel" data-state={status}>
    <header><h2>{title}</h2><span className="state-label">{status}</span></header>
    {children ?? <p>Data tidak tersedia.</p>}
  </section>;
}
