import Link from "next/link";
import { PoRoot, TraderCard, type TraderPayload } from "@/components/TraderCard";
import { api } from "@/lib/api";
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
  try {
    data = (await api.trader(uid)) as TraderPayload;
  } catch {
    data = null;
  }
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
            <p className="note">Нет в рейтинге. Нужна регистрация.</p>
          </>
        )}
      </div>
    </main>
    </PoRoot>
  );
}
