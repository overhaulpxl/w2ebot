import { OperatorNav } from "@/components/OperatorNav";

export default function OperatorLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="economy-shell">
      <header className="economy-header">
        <h1>W2E Operator Panel</h1>
      </header>
      <OperatorNav />
      {children}
    </main>
  );
}