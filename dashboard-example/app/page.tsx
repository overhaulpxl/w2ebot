// app/page.tsx
//
// Halaman dashboard (Server Component). READ diambil di server lewat botGet,
// jadi token aman & tanpa masalah CORS. Render dioper ke DashboardShell (CRM layout).

import {
  botGet,
  type SummaryResponse,
  type LeaderboardResponse,
  type BotStats,
  type Channel,
  type AnnounceConfig,
  type MarketData,
  type LevelDistribution,
  type MarketplaceV1Status,
  type CasinoV1Status,
} from "@/lib/botApi";
import { DashboardShell } from "@/components/DashboardShell";
import { ToastProvider } from "@/components/Toast";

export const dynamic = "force-dynamic"; // selalu ambil data terbaru

export default async function DashboardPage() {
  let summary: SummaryResponse | null = null;
  let leaderboard: LeaderboardResponse | null = null;
  let botStats: BotStats | null = null;
  let channels: Channel[] = [];
  let announceConfig: AnnounceConfig | null = null;
  let market: MarketData | null = null;
  let levels: LevelDistribution | null = null;
  let marketplace: MarketplaceV1Status | null = null;
  let casino: CasinoV1Status | null = null;
  let loadError: string | null = null;

  try {
    [summary, leaderboard, botStats, channels, announceConfig, market, levels, marketplace, casino] = await Promise.all([
      botGet<SummaryResponse>("/api/stats/summary"),
      botGet<LeaderboardResponse>("/api/leaderboard?sort=coins&limit=10"),
      botGet<BotStats>("/api/bot/stats"),
      botGet<Channel[]>("/api/channels"),
      botGet<AnnounceConfig>("/api/announce-config"),
      botGet<MarketData>("/api/market"),
      botGet<LevelDistribution>("/api/economy/level-distribution"),
      botGet<MarketplaceV1Status>("/api/economy/v1-marketplace"),
      botGet<CasinoV1Status>("/api/economy/v1-casino"),
    ]);
  } catch (e: any) {
    loadError = e.message;
  }

  return (
    <ToastProvider>
      {/* Ambient iridescent background (liquid glass) */}
      <div className="bg-blobs" aria-hidden="true">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
      </div>

      <DashboardShell
        summary={summary}
        leaderboard={leaderboard}
        botStats={botStats}
        channels={channels}
        announceConfig={announceConfig}
        market={market}
        levels={levels}
        marketplace={marketplace}
        casino={casino}
        loadError={loadError}
      />
    </ToastProvider>
  );
}
