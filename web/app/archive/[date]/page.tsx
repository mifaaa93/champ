import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

function money(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}

function pct(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function when(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    timeZone: "Africa/Johannesburg",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type Winner = {
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
};

function WinnerCard({ w, kind }: { w: Winner; kind: "yield" | "loss" }) {
  return (
    <article className="card" style={{ marginBottom: 12 }}>
      <h3>
        {w.place} место · {w.nickname || w.uid}
      </h3>
      <p className="mono">
        UID <Link href={`/trader/${w.uid}`}>{w.uid}</Link>
        {w.telegram ? ` · @${w.telegram}` : ""}
        {w.country ? ` · ${w.country}` : ""}
      </p>
      <p className={`mono ${w.pnl < 0 ? "down" : "up"}`}>
        {kind === "yield" ? "Доходность" : "Просадка"} {kind === "yield" ? pct(w.return_pct ?? w.metric) : money(w.pnl)}
      </p>
      <p className="mono">Приз {money(w.prize_amount).replace("+", "")}</p>
      {w.prize_note ? <p className="note">{w.prize_note}</p> : null}
      <p className="mono">Баланс на финише {w.balance != null ? `$${w.balance.toFixed(2)}` : "—"}</p>
      <p className="mono">Старт {w.start_balance != null ? `$${w.start_balance.toFixed(2)}` : "—"}</p>
      <p className="mono">Депозит {w.deposits != null ? `$${w.deposits.toFixed(2)}` : "—"}</p>
      <p className="mono">Вывод {w.withdrawals != null ? `$${w.withdrawals.toFixed(2)}` : "—"}</p>
      <p className="mono">Бонусы {w.bonuses != null ? `$${w.bonuses.toFixed(2)}` : "—"}</p>
      <p className="mono">Торговый PnL {money(w.trading_pnl)}</p>
      <p className="mono">Сделок {w.trades ?? "—"}</p>
    </article>
  );
}

export default async function ArchiveDayPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  let data: Awaited<ReturnType<typeof api.archiveDay>> | null = null;
  try {
    data = await api.archiveDay(date);
  } catch {
    data = null;
  }
  if (!data) {
    return (
      <main className="wrap">
        <p>
          <Link href="/archive">← Архив</Link>
        </p>
        <h1>{date}</h1>
        <p className="note">День ещё не зафиксирован.</p>
      </main>
    );
  }
  return (
    <main className="wrap">
      <p>
        <Link href="/archive">← Архив</Link>
      </p>
      <div className="kicker">FINAL</div>
      <h1>Итоги {data.day}</h1>
      <p className="note">Закрыт {when(data.frozen_at)} UTC+2</p>
      <div className="grid-2">
        <div>
          <h2>Доходность</h2>
          {(data.winners.yield || []).length === 0 ? (
            <p className="note">Нет призовых мест.</p>
          ) : (
            (data.winners.yield || []).map((w) => <WinnerCard key={w.uid} w={w} kind="yield" />)
          )}
        </div>
        <div>
          <h2>Просадка</h2>
          {(data.winners.loss || []).length === 0 ? (
            <p className="note">Нет призовых мест.</p>
          ) : (
            (data.winners.loss || []).map((w) => <WinnerCard key={w.uid} w={w} kind="loss" />)
          )}
        </div>
      </div>
    </main>
  );
}
