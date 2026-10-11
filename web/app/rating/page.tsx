import { Board } from "@/components/Board";
import { Lookup } from "@/components/Lookup";
import { Nav } from "@/components/Nav";

export const dynamic = "force-dynamic";

export default function RatingPage() {
  return (
    <>
    <Nav />
    <main className="wrap">
      <div className="kicker">DAY</div>
      <h1>Доходность и просадка</h1>
      <p className="lead">Открытые метрики того же чемпионата за текущие сутки UTC+2.</p>
      <Lookup />
      <Board />
    </main>
    </>
  );
}
