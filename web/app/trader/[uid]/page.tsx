import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TraderPage({ params }: { params: Promise<{ uid: string }> }) {
  const { uid } = await params;
  let data: Awaited<ReturnType<typeof api.trader>> | null = null;
  try {
    data = await api.trader(uid);
  } catch {
    data = null;
  }
  if (!data) {
    return (
      <main className="wrap">
        <h1>UID {uid}</h1>
        <p className="note">Нет в рейтинге. Нужна регистрация.</p>
      </main>
    );
  }
  const l = data.ledger;
  return (
    <main className="wrap">
      <div className="kicker">TRADER</div>
      <h1>{data.nickname || data.uid}</h1>
      <p className="note">{data.registered ? "Зарегистрирован на сайте" : "Нет регистрации"}</p>
      {l ? (
        <section className="grid-2">
          <article className="card">
            <h3>Сегодня</h3>
            <p className="mono">Баланс ${l.balance.toFixed(2)}</p>
            <p className={`mono ${l.pnl >= 0 ? "up" : "down"}`}>PnL ${l.pnl.toFixed(2)}</p>
            <p className="mono">{l.return_pct.toFixed(2)}%</p>
          </article>
          <article className="card">
            <h3>Движение дня</h3>
            <p className="mono">Депозит ${l.deposits.toFixed(2)}</p>
            <p className="mono">Вывод ${l.withdrawals.toFixed(2)}</p>
            <p className="mono">Бонусы ${l.bonuses.toFixed(2)}</p>
            <p className="note">{l.eligible ? "в зачёте" : l.dq_reason}</p>
          </article>
        </section>
      ) : (
        <p className="note">Снимка за сегодня ещё нет.</p>
      )}
    </main>
  );
}
