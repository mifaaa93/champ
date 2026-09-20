export type Meta = {
  timezone: string;
  now: string;
  day: string;
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
      winners: {
        yield?: { place: number; uid: number; prize_amount: number; prize_note: string }[];
        loss?: { place: number; uid: number; prize_amount: number; prize_note: string }[];
      };
    }>(`/public/archive/${day}`),
  trader: (uid: string) =>
    getJSON<{
      uid: number;
      nickname: string;
      registered: boolean;
      day: string;
      ledger: {
        uid: number;
        nickname: string;
        balance: number;
        pnl: number;
        return_pct: number;
        deposits: number;
        withdrawals: number;
        bonuses: number;
        eligible: boolean;
        dq_reason?: string;
        snapshot_ts?: string | null;
      } | null;
    }>(`/public/trader/${uid}`),
};
