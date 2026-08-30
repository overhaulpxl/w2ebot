import Link from "next/link";

export function OperatorNav() {
  return (
    <nav className="economy-nav">
      <Link href="/operator">Manajemen User</Link>
      <Link href="/operator/rpg">RPG & Bos</Link>
      <Link href="/operator/market">Marketplace</Link>
      <Link href="/operator/casino">Casino & Options</Link>
      <Link href="/operator/crypto">Crypto & Mining</Link>
      <Link href="/operator/giveaway">Giveaway</Link>
    </nav>
  );
}