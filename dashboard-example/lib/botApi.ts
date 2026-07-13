// lib/botApi.ts
//
// Helper untuk memanggil W2E Bot API.
// botGet  -> boleh dipakai di server maupun (versi public) di client.
// botPost -> HANYA boleh dipakai di server (Route Handler / Server Action),
//            karena membawa DASHBOARD_TOKEN.

const SERVER_BASE = process.env.BOT_API_URL ?? "http://localhost:8081";
const TOKEN = process.env.DASHBOARD_TOKEN ?? "";

/** GET ke bot API (server-side, tanpa cache). */
export async function botGet<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${SERVER_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as any).error || `GET ${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/**
 * POST ke bot API dengan token. WAJIB dipanggil dari server saja.
 * Melempar Error berisi pesan dari bot kalau gagal (termasuk 401/409/400).
 */
export async function botPost<T = unknown>(
  path: string,
  body: unknown,
): Promise<T> {
  if (!TOKEN) {
    throw new Error("DASHBOARD_TOKEN belum di-set di server Next.js");
  }
  const res = await fetch(`${SERVER_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Token": TOKEN,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as any).error || `POST ${path} -> ${res.status}`);
  }
  return data as T;
}

/**
 * GET ke bot API dengan token (untuk endpoint read token-gated, mis. /api/audit).
 * WAJIB dipanggil dari server saja.
 */
export async function botGetToken<T = unknown>(path: string): Promise<T> {
  if (!TOKEN) {
    throw new Error("DASHBOARD_TOKEN belum di-set di server Next.js");
  }
  const res = await fetch(`${SERVER_BASE}${path}`, {
    headers: { "X-Auth-Token": TOKEN },
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as any).error || `GET ${path} -> ${res.status}`);
  }
  return data as T;
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
  id: number;
  ts: string;
  action: string;
  target_id: string | null;
  detail: string | null;
  source: string;
}

export interface AuditResponse {
  limit: number;
  entries: AuditEntry[];
}
