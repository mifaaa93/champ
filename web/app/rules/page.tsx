import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function RulesPage() {
  let min = 50;
  let top = 7;
  try {
    const meta = await api.meta();
    min = meta.min_day_deposit;
    top = meta.top_n;
  } catch {
    /* defaults */
  }
  return (
    <main className="wrap">
      <div className="kicker">RULES</div>
      <h1>Как считается день</h1>
      <div className="grid-2">
        <article className="card">
          <h3>Вход</h3>
          <p className="note">
            1. Регистрация на этом сайте с UID Pocket Option из нашего партнёрского контура.
            <br />
            2. Депозит от ${min} в текущие сутки Dubai. Вчерашний депозит не считается.
          </p>
        </article>
        <article className="card">
          <h3>Окно</h3>
          <p className="note">
            Сутки 00:00–23:59 Asia/Dubai. Публикация топ-{top} каждый час. Freeze в 23:59.
          </p>
        </article>
        <article className="card">
          <h3>Формула</h3>
          <p className="note">
            PnL = (баланс сейчас − баланс на старте дня) − депозиты дня − бонусы дня.
            <br />
            Вывод не прибавляется обратно: если вывести деньги до конца дня, место падает.
          </p>
        </article>
        <article className="card">
          <h3>Призы</h3>
          <p className="note">
            A — максимальная доходность %. B — максимальная просадка, компенсация процентом от
            убытка с капом. Один UID не берёт обе номинации: приоритет у A.
          </p>
        </article>
      </div>
    </main>
  );
}
