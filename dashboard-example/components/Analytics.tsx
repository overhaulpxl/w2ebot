// components/Analytics.tsx
//
// Section Analitik: chart tren harga market (line) + distribusi level pemain (bar).
// Pakai recharts. Aksesibilitas: tabel alternatif tersembunyi + judul + respect
// prefers-reduced-motion (animasi chart dimatikan kalau user minta).
"use client";

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { MarketData, LevelDistribution } from "@/lib/botApi";

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const handler = () => setReduced(mq.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}

const tooltipStyle = {
  background: "rgba(20, 27, 48, 0.95)",
  border: "1px solid rgba(255,255,255,0.16)",
  borderRadius: 10,
  color: "#f3f5ff",
  fontSize: 13,
};

export function Analytics({
  market,
  levels,
}: {
  market: MarketData | null;
  levels: LevelDistribution | null;
}) {
  const reduced = useReducedMotion();
  const symbols = market ? Object.keys(market.coins) : [];
  const [symbol, setSymbol] = useState<string>(symbols[0] ?? "");

  const coin = market && symbol ? market.coins[symbol] : null;
  const lineData =
    coin?.history.map((price, i) => ({ t: `#${i + 1}`, price })) ?? [];
  const barData = levels?.buckets.map((b) => ({ level: `Lv${b.level}`, count: b.count })) ?? [];

  return (
    <div className="stack">
      {/* Tren harga market */}
      <section className="card card-pad" aria-labelledby="chart-market">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            marginBottom: 16,
          }}
        >
          <h3 id="chart-market">Tren Harga Market</h3>
          {symbols.length > 0 && (
            <select
              className="select"
              style={{ width: "auto", minWidth: 160 }}
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              aria-label="Pilih koin kripto"
            >
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s} {market?.coins[s].name ? `— ${market.coins[s].name}` : ""}
                </option>
              ))}
            </select>
          )}
        </div>

        {coin && lineData.length > 0 ? (
          <>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <LineChart data={lineData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="t" stroke="#8b93bd" fontSize={12} tickLine={false} />
                  <YAxis stroke="#8b93bd" fontSize={12} tickLine={false} width={56} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: any) => [`${v} koin`, "Harga"]} />
                  <Line
                    type="monotone"
                    dataKey="price"
                    stroke="#7c83ff"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: "#7c83ff" }}
                    isAnimationActive={!reduced}
                    animationDuration={400}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            {/* Tabel alternatif untuk screen reader */}
            <table className="sr-only">
              <caption>Riwayat harga {symbol}</caption>
              <thead>
                <tr>
                  <th>Titik</th>
                  <th>Harga</th>
                </tr>
              </thead>
              <tbody>
                {lineData.map((d) => (
                  <tr key={d.t}>
                    <td>{d.t}</td>
                    <td>{d.price}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <div className="faint">Data market belum tersedia.</div>
        )}
      </section>

      {/* Distribusi level pemain */}
      <section className="card card-pad" aria-labelledby="chart-levels">
        <h3 id="chart-levels" style={{ marginBottom: 16 }}>
          Distribusi Level Pemain
        </h3>
        {barData.length > 0 ? (
          <>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={barData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="level" stroke="#8b93bd" fontSize={12} tickLine={false} />
                  <YAxis stroke="#8b93bd" fontSize={12} tickLine={false} width={48} allowDecimals={false} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    cursor={{ fill: "rgba(255,255,255,0.06)" }}
                    formatter={(v: any) => [`${v} pemain`, "Jumlah"]}
                  />
                  <Bar
                    dataKey="count"
                    fill="#22d3ee"
                    radius={[6, 6, 0, 0]}
                    isAnimationActive={!reduced}
                    animationDuration={400}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="sr-only">
              <caption>Distribusi level pemain</caption>
              <thead>
                <tr>
                  <th>Level</th>
                  <th>Jumlah pemain</th>
                </tr>
              </thead>
              <tbody>
                {barData.map((d) => (
                  <tr key={d.level}>
                    <td>{d.level}</td>
                    <td>{d.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <div className="faint">Belum ada data level.</div>
        )}
      </section>
    </div>
  );
}
