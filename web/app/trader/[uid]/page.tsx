import Link from "next/link";
import { PoRoot, TraderCard, type TraderPayload } from "@/components/TraderCard";
import { api } from "@/lib/api";
import { headers } from "next/headers";
import "@/app/event.css";

export const dynamic = "force-dynamic";

export default async function TraderPage({
  params,
  searchParams,
}: {
  params: Promise<{ uid: string }>;
  searchParams: Promise<{ from?: string }>;
}) {
  const { uid } = await params;
  const { from } = await searchParams;
  const backHref = from === "admin" ? "/admin#participants" : "/";
  const backLabel = from === "admin" ? "← К участникам" : "← К чемпионату";
  let data: TraderPayload | null = null;
  let history: { participation_days: number; daily_first_places: number; daily_prizes_usdt: number; results: { day: string; nomination: string; place: number; pnl: number; usdt: number }[] } | null = null;
  try {
    data = (await api.trader(uid)) as TraderPayload;
  } catch {
    data = null;
  }
  try {
    const ip = process.env.WEB_SOCKET_IP_STAMPED === "1"
      ? (await headers()).get("x-real-ip") || "unknown"
      : "unknown";
    const response = await fetch(`${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/public/history/${uid}`, {
      cache: "no-store",
      headers: { "X-Real-IP": ip },
    });
    if (response.ok) history = await response.json();
  } catch { /* archive unavailable */ }
  return (
    <PoRoot>
    <main className="po">
      <div className="container">
        <p>
          <Link className="help-link" href={backHref}>
            {backLabel}
          </Link>
        </p>
        {data ? (
          <TraderCard data={data} canEdit={from === "admin"} />
        ) : (
          <>
            <h1 className="section-title" style={{ textAlign: "left" }}>
              UID {uid}
            </h1>
            <p className="note">Нет текущего профиля. История доступна без регистрации на сайте.</p>
          </>
        )}
        {history && <div className="profile-panel">
          <h3>Дневная история UID</h3>
          <p className="note">Дней участия: {history.participation_days} · первых мест в дневных номинациях: {history.daily_first_places} · дневные призы: {history.daily_prizes_usdt.toFixed(2)} USDT</p>
          {history.results.map((item, i) => <p className="note" key={`${item.day}-${i}`}>
            {item.day} · {item.nomination === "yield" ? "Доходность" : "Просадка"} · #{item.place} · PnL ${item.pnl.toFixed(2)} · {item.usdt.toFixed(2)} USDT
          </p>)}
        </div>}
      </div>
    </main>
    </PoRoot>
  );
}
