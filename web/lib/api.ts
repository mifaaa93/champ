export type Meta = {
  timezone: string;
  now: string;
  day: string;
  day_end: string;
  seconds_to_close: number;
  top_n: number;
  min_day_deposit: number;
  prize_yield: number[];
  prize_loss_pct: number[];
  loss_comp_cap: number;
  prize_places: number;
};

export type BoardRow = {
  place: number;
  uid: number;
  nickname: string;
  balance: number;
  pnl: number;
  return_pct: number;
  deposits: number;
  withdrawals: number;
  bonuses: number;
  eligible: boolean;
};

function base() {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
  }
  return "/backend";
}

export function apiPath(path: string) {
  return `${base()}${path}`;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(apiPath(path), { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => getJSON<Meta>("/public/meta"),
  board: (nom: "yield" | "loss") =>
    getJSON<{ day: string; rows: BoardRow[] }>(`/public/leaderboard?nomination=${nom}`),
  archive: () => getJSON<{ days: string[] }>("/public/archive"),
  archiveDay: (day: string) =>
    getJSON<{
      day: string;
      frozen?: boolean;
      frozen_at?: string | null;
      winners: {
        yield?: {
          place: number;
          uid: number;
          nickname?: string;
          telegram?: string;
          country?: string;
          metric: number;
          pnl: number;
          prize_amount: number;
          prize_note: string;
          balance?: number | null;
          start_balance?: number | null;
          deposits?: number | null;
          withdrawals?: number | null;
          bonuses?: number | null;
          return_pct?: number | null;
          trading_pnl?: number | null;
          trades?: number | null;
        }[];
        loss?: {
          place: number;
          uid: number;
          nickname?: string;
          telegram?: string;
          country?: string;
          metric: number;
          pnl: number;
          prize_amount: number;
          prize_note: string;
          balance?: number | null;
          start_balance?: number | null;
          deposits?: number | null;
          withdrawals?: number | null;
          bonuses?: number | null;
          return_pct?: number | null;
          trading_pnl?: number | null;
          trades?: number | null;
        }[];
      };
    }>(`/public/archive/${day}`),
  trader: (uid: string) =>
    getJSON<{
      uid: number;
      nickname: string;
      telegram?: string;
      country?: string;
      registered: boolean;
      registered_at?: string | null;
      last_checked_at?: string | null;
      day: string;
      ledger: {
        uid: number;
        nickname: string;
        balance: number;
        start_balance: number;
        pnl: number;
        trading_pnl?: number;
        return_pct: number;
        deposits: number;
        withdrawals: number;
        bonuses: number;
        basis?: number;
        eligible: boolean;
        dq_reason?: string;
        start_ts?: string | null;
        snapshot_ts?: string | null;
        trades?: number;
        status?: string;
        self_excluded?: boolean;
      } | null;
    }>(`/public/trader/${uid}`),
};
