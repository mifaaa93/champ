import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ArchivePage() {
  let days: string[] = [];
  try {
    days = (await api.archive()).days;
  } catch {
    days = [];
  }
  return (
    <main className="wrap">
      <div className="kicker">ARCHIVE</div>
      <h1>Закрытые дни</h1>
      <div className="card">
        {days.length === 0 ? (
          <p className="note">Пока нет зафиксированных итогов.</p>
        ) : (
          <ul>
            {days.map((d) => (
              <li key={d}>
                <Link href={`/archive/${d}`}>{d}</Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
