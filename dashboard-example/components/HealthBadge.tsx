export function HealthBadge({ health }: { health: string }) {
  return <span className="health-badge" data-health={health}>{health.replaceAll("_", " ")}</span>;
}
