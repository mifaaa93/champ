"use client";

import { useEffect, useState } from "react";

type PrizeRow = { place: string; amount: number; suffix?: string };
type Activity = { name: string; action: string; rank?: number | null; extra?: string; time?: string };
type ShowcaseRow = { place: number; name: string; dep: number; turn: number; uid?: number | null };

type EventForm = {
  event_name: string;
  event_end: string;
  prize_pool: number;
  prize_table: PrizeRow[];
  telegram_channel_url: string;
  rami_url: string;
  event_rules: string;
  activity: Activity[];
};

function toLocalInput(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function EventPanel({
  adminFetch,
  onStatus,
  onError,
}: {
  adminFetch: (path: string, method?: string, body?: unknown) => Promise<unknown>;
  onStatus: (s: string) => void;
  onError: (s: string) => void;
}) {
  const [form, setForm] = useState<EventForm | null>(null);
  const [top, setTop] = useState<ShowcaseRow[]>([]);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    let dead = false;
    void (async () => {
      try {
        const s = (await adminFetch("/admin/settings")) as Record<string, unknown>;
        const sc = (await adminFetch("/admin/showcase")) as { rows: ShowcaseRow[] };
        if (dead) return;
        setForm({
          event_name: String(s.event_name || "PO TOURNAMENT"),
          event_end: String(s.event_end || ""),
          prize_pool: Number(s.prize_pool || 0),
          prize_table: (s.prize_table as PrizeRow[]) || [],
          telegram_channel_url: String(s.telegram_channel_url || ""),
          rami_url: String(s.rami_url || ""),
          event_rules: ((s.event_rules as string[]) || []).join("\n"),
          activity: ((s.activity as Activity[]) || []).slice(0, 8),
        });
        setTop(sc.rows || []);
      } catch (e) {
        if (!dead) onError(e instanceof Error ? e.message : "не загрузилось");
      }
    })();
    return () => {
      dead = true;
    };
    // load once per mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!form) return <p className="note">Загрузка ивента…</p>;

  async function saveSettings(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setBusy("set");
    onError("");
    try {
      const parsed = new Date(form.event_end);
      const endIso = Number.isNaN(parsed.getTime())
        ? new Date(Date.now() + 14 * 86400000).toISOString()
        : parsed.toISOString();
      await adminFetch("/admin/settings", "PATCH", {
        event_name: form.event_name,
        event_end: endIso,
        prize_pool: Number(form.prize_pool),
        prize_table: form.prize_table.map((p) => ({
          place: p.place,
          amount: Number(p.amount),
          suffix: p.suffix || "",
        })),
        telegram_channel_url: form.telegram_channel_url,
        rami_url: form.rami_url,
        event_rules: form.event_rules
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
        activity: form.activity,
      });
      onStatus("Ивент сохранён");
    } catch (err) {
      onError(err instanceof Error ? err.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  async function saveTop(e: React.FormEvent) {
    e.preventDefault();
    setBusy("top");
    onError("");
    try {
      await adminFetch("/admin/showcase", "PUT", {
        rows: top.map((r) => ({
          place: r.place,
          name: r.name,
          dep: Number(r.dep),
          turn: Number(r.turn),
          uid: r.uid || null,
        })),
      });
      onStatus("Витрина топ-10 сохранена");
    } catch (err) {
      onError(err instanceof Error ? err.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <form className="form wide card" onSubmit={(e) => void saveSettings(e)}>
        <h2>Сезон / ивент</h2>
        <div className="form-grid">
          <label>
            Название
            <input
              value={form.event_name}
              onChange={(e) => setForm({ ...form, event_name: e.target.value })}
            />
          </label>
          <label>
            Конец турнира
            <input
              type="datetime-local"
              value={toLocalInput(form.event_end)}
              onChange={(e) => setForm({ ...form, event_end: e.target.value })}
            />
          </label>
          <label>
            Призовой фонд, $
            <input
              type="number"
              value={form.prize_pool}
              onChange={(e) => setForm({ ...form, prize_pool: Number(e.target.value) })}
            />
          </label>
          <label>
            Telegram-канал
            <input
              value={form.telegram_channel_url}
              onChange={(e) => setForm({ ...form, telegram_channel_url: e.target.value })}
            />
          </label>
          <label>
            Ссылка Rami
            <input value={form.rami_url} onChange={(e) => setForm({ ...form, rami_url: e.target.value })} />
          </label>
        </div>
        <h3>Призы</h3>
        {form.prize_table.map((p, i) => (
          <div className="form-grid" key={i}>
            <label>
              Место
              <input
                value={p.place}
                onChange={(e) => {
                  const prize_table = form.prize_table.slice();
                  prize_table[i] = { ...p, place: e.target.value };
                  setForm({ ...form, prize_table });
                }}
              />
            </label>
            <label>
              Сумма $
              <input
                type="number"
                value={p.amount}
                onChange={(e) => {
                  const prize_table = form.prize_table.slice();
                  prize_table[i] = { ...p, amount: Number(e.target.value) };
                  setForm({ ...form, prize_table });
                }}
              />
            </label>
            <label>
              Суффикс
              <input
                value={p.suffix || ""}
                onChange={(e) => {
                  const prize_table = form.prize_table.slice();
                  prize_table[i] = { ...p, suffix: e.target.value };
                  setForm({ ...form, prize_table });
                }}
              />
            </label>
          </div>
        ))}
        <label>
          Правила (по строке)
          <textarea
            rows={8}
            value={form.event_rules}
            onChange={(e) => setForm({ ...form, event_rules: e.target.value })}
          />
        </label>
        <h3>Лента действий</h3>
        {form.activity.map((a, i) => (
          <div className="form-grid" key={i}>
            <label>
              Имя
              <input
                value={a.name}
                onChange={(e) => {
                  const activity = form.activity.slice();
                  activity[i] = { ...a, name: e.target.value };
                  setForm({ ...form, activity });
                }}
              />
            </label>
            <label>
              Действие
              <input
                value={a.action}
                onChange={(e) => {
                  const activity = form.activity.slice();
                  activity[i] = { ...a, action: e.target.value };
                  setForm({ ...form, activity });
                }}
              />
            </label>
            <label>
              Место
              <input
                value={a.rank ?? ""}
                onChange={(e) => {
                  const activity = form.activity.slice();
                  const n = e.target.value ? Number(e.target.value) : null;
                  activity[i] = { ...a, rank: n };
                  setForm({ ...form, activity });
                }}
              />
            </label>
            <label>
              Доп.
              <input
                value={a.extra || ""}
                onChange={(e) => {
                  const activity = form.activity.slice();
                  activity[i] = { ...a, extra: e.target.value };
                  setForm({ ...form, activity });
                }}
              />
            </label>
            <label>
              Время
              <input
                value={a.time || ""}
                onChange={(e) => {
                  const activity = form.activity.slice();
                  activity[i] = { ...a, time: e.target.value };
                  setForm({ ...form, activity });
                }}
              />
            </label>
          </div>
        ))}
        <button className="cta" type="submit" disabled={busy === "set"}>
          {busy === "set" ? "Сохраняем…" : "Сохранить ивент"}
        </button>
      </form>

      <form className="form wide card" onSubmit={(e) => void saveTop(e)}>
        <h2>Витрина топ-10</h2>
        <p className="note">
          Имена и цифры пустышек на главной. Участники и общий оборот считаются сами: пустышки + кто
          зарегистрировался.
        </p>
        {top.map((row, i) => (
          <div className="form-grid" key={row.place}>
            <label>
              #{row.place} имя
              <input
                value={row.name}
                onChange={(e) => {
                  const next = top.slice();
                  next[i] = { ...row, name: e.target.value };
                  setTop(next);
                }}
              />
            </label>
            <label>
              Деп $
              <input
                type="number"
                value={row.dep}
                onChange={(e) => {
                  const next = top.slice();
                  next[i] = { ...row, dep: Number(e.target.value) };
                  setTop(next);
                }}
              />
            </label>
            <label>
              Оборот $
              <input
                type="number"
                value={row.turn}
                onChange={(e) => {
                  const next = top.slice();
                  next[i] = { ...row, turn: Number(e.target.value) };
                  setTop(next);
                }}
              />
            </label>
          </div>
        ))}
        <button className="cta" type="submit" disabled={busy === "top"}>
          {busy === "top" ? "Сохраняем…" : "Сохранить витрину"}
        </button>
      </form>
    </>
  );
}
