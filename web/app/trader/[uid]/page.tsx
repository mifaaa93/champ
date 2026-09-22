import Link from "next/link";
import { TraderCard, type TraderPayload } from "@/components/TraderCard";
import { api } from "@/lib/api";

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
  const backHref = from === "admin" ? "/admin#users" : "/rating";
  const backLabel = from === "admin" ? "← К списку зарегистрированных" : "← К рейтингу";
  let data: TraderPayload | null = null;
  try {
    data = (await api.trader(uid)) as TraderPayload;
  } catch {
    data = null;
  }
  if (!data) {
    return (
      <main className="wrap">
        <p>
          <Link href={backHref}>{backLabel}</Link>
        </p>
        <h1>UID {uid}</h1>
        <p className="note">Нет в рейтинге. Нужна регистрация.</p>
      </main>
    );
  }
  return (
    <main className="wrap">
      <p>
        <Link href={backHref}>{backLabel}</Link>
      </p>
      <div className="kicker">TRADER</div>
      <TraderCard data={data} canEdit={from === "admin"} />
    </main>
  );
}
