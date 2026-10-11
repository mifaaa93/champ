import { Board } from "@/components/Board";
import { Lookup } from "@/components/Lookup";
import { Nav } from "@/components/Nav";

export const dynamic = "force-dynamic";

export default function RatingPage() {
  return (
    <>
    <Nav />
    <main className="wrap">
      <div className="kicker">LIVE BOARD</div>
      <h1>Рейтинг дня</h1>
      <p className="lead">Топ обновляется со снимков баланса. Вывод в течение суток снижает место в доходности.</p>
      <Lookup />
      <Board />
    </main>
    </>
  );
}
