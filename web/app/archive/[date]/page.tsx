import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

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
        <h1>{date}</h1>
        <p className="note">День ещё не зафиксирован.</p>
      </main>
    );
  }
  return (
    <main className="wrap">
      <div className="kicker">FINAL</div>
      <h1>Итоги {data.day}</h1>
      <div className="grid-2">
        <article className="card">
          <h3>Доходность</h3>
          {(data.winners.yield || []).map((w) => (
            <p key={w.uid} className="mono">
              {w.place}. {w.uid} · ${w.prize_amount.toFixed(2)}
            </p>
          ))}
        </article>
        <article className="card">
          <h3>Просадка</h3>
          {(data.winners.loss || []).map((w) => (
            <p key={w.uid} className="mono">
              {w.place}. {w.uid} · ${w.prize_amount.toFixed(2)}
              <span className="note"> {w.prize_note}</span>
            </p>
          ))}
        </article>
      </div>
    </main>
  );
}
