import Link from "next/link";

const LINKS = [
  ["/economy", "Ringkasan"], ["/economy/supply", "Supply"],
  ["/economy/liabilities", "Liabilitas"], ["/economy/marketplace", "Marketplace"],
  ["/economy/casino-options", "Casino & Options"], ["/economy/crypto-mining", "Crypto & Mining"],
  ["/economy/giveaway", "Giveaway"], ["/economy/recovery", "Recovery"],
  ["/economy/notifications", "Notifikasi"], ["/admin/audit", "Audit"],
  ["/operator", "Operator Panel"],
] as const;

export function EconomyNav() {
  return <nav className="economy-nav" aria-label="Navigasi Economy">
    {LINKS.map(([href, label]) => <Link key={href} href={href}>{label}</Link>)}
  </nav>;
}
