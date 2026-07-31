export function MetricTable({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return <p>{String(value ?? "-")}</p>;
  return <dl className="metric-table">
    {Object.entries(value as Record<string, unknown>).map(([key, item]) =>
      <div key={key}><dt>{key}</dt><dd>{typeof item === "object" ? JSON.stringify(item) : String(item)}</dd></div>)}
  </dl>;
}
