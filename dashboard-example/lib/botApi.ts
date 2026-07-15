// lib/botApi.ts
//
// Seluruh pembacaan melewati sesi dashboard dan envelope internal bertanda tangan.
import "server-only";
import { requireDashboardSession } from "./dashboardAuth";
import { dashboardRead } from "./dashboardReads";

/** GET ke bot API (server-side, tanpa cache). */
export async function botGet<T = unknown>(path: string): Promise<T> {
  const validated = await requireDashboardSession();
  return dashboardRead<T>(path, validated.identity);
}

/**
 * POST ke bot API dengan token. WAJIB dipanggil dari server saja.
 * Melempar Error berisi pesan dari bot kalau gagal (termasuk 401/409/400).
 */
export async function botPost<T = unknown>(
  _path: string,
  _body: unknown,
): Promise<T> {
  throw new Error("legacy_dashboard_write_disabled");
}

/**
 * GET ke bot API dengan token (untuk endpoint read token-gated, mis. /api/audit).
 * WAJIB dipanggil dari server saja.
 */
export async function botGetToken<T = unknown>(path: string): Promise<T> {
  return botGet<T>(path);
}

// ── Tipe ringkas (sesuaikan kalau perlu) ─────────────────────────────────────
export interface SummaryResponse {
  member_count: number;
  members_in_voice: number;
  boss_active: boolean;
  treasury_balance: number;
  total_coins_in_circulation: number;
  v1_enabled?: boolean;
  v1_supply?: EconomyV1Supply;
}

export interface CurrencySupply {
  user_wallet_balances: number;
  spendable_treasury_balances: number;
  locked_reserve_balances: number;
  burn_account_balance: number;
  net_issued_supply: number;
  circulating_supply: number;
  non_circulating_supply: number;
  burned_supply: number;
  issuance_balance: number;
  issuance_matches: boolean;
}

export interface EconomyV1Supply {
  ETM: CurrencySupply;
  ECY: CurrencySupply;
  ledger_zero_sum: boolean;
}

export interface EconomyV1Profile {
  guild_id: string;
  user_id: string;
  level: number;
  xp: number;
  etm_balance: number;
  ecy_balance: number;
  max_hp: number;
  current_hp: number;
  attack: number;
  defense: number;
  crit_bps: number;
  energy: number;
  power_score: number;
  activity_score_30d: number;
  active_weapon_instance_id: string | null;
  active_armor_instance_id: string | null;
  active_accessory_instance_id: string | null;
  active_pet_instance_id: string | null;
  phase3_enabled?: boolean;
  effective_max_hp?: number;
  effective_attack?: number;
  effective_defense?: number;
  effective_crit_bps?: number;
  effective_power_score?: number;
  active_loadout?: Record<
    "weapon" | "armor" | "accessory" | "pet",
    { instance_id: string; name: string; enhancement_level?: number } | null
  >;
}

export interface Phase3BossStatus {
  raidId: string;
  tier: "NORMAL" | "ELITE" | "WORLD";
  maxHp: number;
  currentHp: number;
  status: "ACTIVE" | "DEFEATED" | "AWAITING_FUNDS" | "SETTLED" | "CANCELLED";
  participant_count: number;
  treasury_ready: boolean;
  manual_settlement_required: boolean;
}

export interface MarketplaceV1Status {
  enabled: boolean;
  schema_ready: boolean;
  paused?: boolean;
  unresolved?: number;
  purchase_reviews?: number;
}

export interface CasinoV1Status {
  enabled: boolean;
  schema_ready: boolean;
  seeded?: boolean;
  paused?: boolean;
  bankrollEcy?: number;
  reservedLiabilityEcy?: number;
  availableBankrollEcy?: number;
  exposureCapEcy?: number;
  unresolvedSessions?: number;
  reviewRequired?: number;
}

export interface CryptoV1Status {
  enabled: boolean;
  schema_ready: boolean;
  readiness?: {
    ready: boolean;
    code: string;
    marketReserveEcy?: number;
  };
  market?: MarketData & { available?: boolean; currency?: "ECY"; global?: boolean };
}

export interface MiningV1Status {
  enabled: boolean;
  schema_ready: boolean;
  ready?: boolean;
  code?: string;
  level?: number;
  slotLimit?: number;
}

export interface Phase8Status {
  enabled: boolean;
  schema_ready: boolean;
  paused?: boolean;
  activePositions?: number;
  combinedStakeEcy?: number;
  bankrollEcy?: number;
  reservedLiabilityEcy?: number;
  optionsReservedLiabilityEcy?: number;
  availableBankrollEcy?: number;
  exposureCapEcy?: number;
}

export interface LeaderboardEntry {
  rank: number;
  id: string;
  displayName: string;
  coins: number;
  xp: number;
  level: number;
}

export interface LeaderboardResponse {
  sort: "coins" | "level";
  limit: number;
  entries: LeaderboardEntry[];
}

export interface Channel {
  id: string;
  name: string;
}

// default + 6 kategori. Value = channel ID string, "" = pakai fallback.
export type AnnounceConfig = Record<string, string>;

export const ANNOUNCE_CATEGORIES = [
  "default",
  "market",
  "levelup",
  "birthday",
  "boss",
  "booster",
  "binomo",
] as const;

export const ANNOUNCE_LABELS: Record<string, string> = {
  default: "Default (fallback)",
  market: "Market (pump/dump kripto)",
  levelup: "Level Up (XP voice)",
  birthday: "Ulang Tahun",
  boss: "Boss Raid",
  booster: "Server Booster",
  binomo: "Hasil Binomo",
};

export interface BotStats {
  online: boolean;
  latency_ms: number | null;
  uptime_seconds: number;
  guild: {
    name: string;
    icon_url: string | null;
    member_count: number;
    humans: number | null;
    bots: number;
    members_in_voice: number;
    boosts: number;
    boost_tier: number;
    text_channels: number;
    voice_channels: number;
    roles: number;
  } | null;
  economy: {
    players: number;
    total_coins: number;
    average_level: number;
    max_level: number;
    total_xp: number;
  };
  treasury_balance: number;
  boss_active: boolean;
  commands_registered: number;
  announce_channels_configured: number;
  prefix: string;
}

export interface UserProfile {
  id: string;
  displayName: string;
  coins: number;
  xp: number;
  level: number;
  xp_to_next: number;
  rank: number | null;
  lastDaily: string;
  crypto: Record<string, number>;
  rigs: Record<string, number>;
  items: Record<string, number>;
  pet: string | null;
  achievements: string[];
  total_vc_minutes: number;
  married_to: string | null;
  children: string[];
  bg_url: string | null;
  cooldowns: { work: number; rob: number; pray: number; curse: number };
  top_games?: { game: string; plays: number; wins: number; win_rate: number }[];
  games?: Record<string, { plays: number; wins: number }>;
}

export interface MarketCoin {
  name?: string;
  price: number;
  history: number[];
  emoji?: string;
  basePriceEcy?: number;
  maximumNormalChangeBps?: number;
  volatilityLevel?: "LOW" | "MODERATE" | "HIGH" | "EXTREME";
  updatedAt?: string;
}

export interface MarketData {
  last_updated?: string;
  coins: Record<string, MarketCoin>;
}

export interface LevelBucket {
  level: number;
  count: number;
}

export interface LevelDistribution {
  buckets: LevelBucket[];
}

export interface AuditEntry {
  auditId: string;
  executorUserId: string;
  permissionClass: string;
  operationType: string;
  targetType: string;
  targetId: string;
  requestId: string;
  resultStatus: string;
  createdAt: string;
}

export interface AuditResponse {
  entries: AuditEntry[];
}
