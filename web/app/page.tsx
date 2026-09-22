import Link from "next/link";
import { Countdown } from "@/components/Countdown";
import { Board } from "@/components/Board";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  let seconds = 0;
  let dayEnd = "";
  let min = 50;
  let prizes: number[] = [100, 50, 25];
  let loss = [15, 10, 5];
  try {
    const meta = await api.meta();
    seconds = meta.seconds_to_close;
    dayEnd = meta.day_end;
    min = meta.min_day_deposit;
    prizes = meta.prize_yield;
    loss = meta.prize_loss_pct;
  } catch {
    seconds = 0;
  }

  return (
    <main className="wrap">
      <section className="hero">
        <div>
          <div className="kicker">Pocket Option · дневной кубок</div>
          <h1>Дневной кубок. Две номинации. Автоматический зачёт.</h1>
          <p className="lead">
            Регистрируешься на сайте, вносишь от ${min} сегодня по UTC+2 — и попадаешь в живой
            топ-7. Вывод до конца суток снижает место. Бонусы в доходность не входят.
          </p>
          <p>
            <Link className="cta" href="/register">
              Зайти в кубок
            </Link>
            &nbsp;&nbsp;
            <Link className="cta ghost" href="/rules">
              Правила
            </Link>
          </p>
        </div>
        <Countdown seconds={seconds} dayEnd={dayEnd} />
      </section>

      <section className="grid-2">
        <article className="card">
          <h3>Номинация A — доходность</h3>
          <p className="note">Топ по % за сутки. Призовые места: {prizes.map((x) => `$${x}`).join(" / ")}.</p>
        </article>
        <article className="card">
          <h3>Номинация B — просадка</h3>
          <p className="note">
            Компенсация {loss.join(" / ")}% торгового убытка (с капом). Вывод в эту номинацию не
            помогает. Один UID не забирает обе: приоритет у доходности.
          </p>
        </article>
      </section>

      <h2 style={{ marginTop: 36 }}>Живой топ</h2>
      <Board />
    </main>
  );
}
