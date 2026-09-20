import { Board } from "@/components/Board";

export const dynamic = "force-dynamic";

export default function RatingPage() {
  return (
    <main className="wrap">
      <div className="kicker">LIVE BOARD</div>
      <h1>Рейтинг дня</h1>
      <p className="lead">Топ-7 обновляется со снимков баланса. Вывод в течение суток снижает место.</p>
      <Board />
    </main>
  );
}
