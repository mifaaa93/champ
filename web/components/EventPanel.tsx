"use client";

import { useEffect, useState } from "react";

type PrizeRow = { place: string; amount: number; suffix?: string };
type ShowcaseRow = {
  place: number;
  name: string;
  dep: number;
  turn: number;
  balance: number;
  pnl: number;
  return_pct: number;
  uid?: number | null;
  randomize?: boolean;
};

type EventForm = {
  event_name: string;
  event_start: string;
  event_end: string;
  event_min_deposit: number;
  dummy_tick_minutes: number;
  prize_pool: number;
  prize_table: PrizeRow[];
  telegram_channel_url: string;
  rami_url: string;
  event_rules: string;
};

function toLocalInput(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function money(n: number) {
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

function emptyRow(place: number): ShowcaseRow {
  return {
    place,
    name: "",
    dep: 50,
    turn: 0,
    balance: 0,
    pnl: 0,
    return_pct: 0,
    uid: null,
    randomize: true,
  };
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
  const [edit, setEdit] = useState<ShowcaseRow | null>(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    let dead = false;
    void (async () => {
      try {
        const s = (await adminFetch("/admin/settings")) as Record<string, unknown>;
        const sc = (await adminFetch("/admin/showcase")) as { rows: ShowcaseRow[] };
        if (dead) return;
        setForm({
          event_name: String(s.event_name || "PO CHAMPIONSHIP"),
          event_start: String(s.event_start || ""),
          event_end: String(s.event_end || ""),
          event_min_deposit: Number(s.event_min_deposit || 50),
          dummy_tick_minutes: Number(s.dummy_tick_minutes || 1),
          prize_pool: Number(s.prize_pool || 0),
          prize_table: (s.prize_table as PrizeRow[]) || [],
          telegram_channel_url: String(s.telegram_channel_url || ""),
          rami_url: String(s.rami_url || ""),
          event_rules: ((s.event_rules as string[]) || []).join("\n"),
        });
        setTop(
          (sc.rows || []).map((r) => ({
            ...emptyRow(r.place),
            ...r,
            randomize: r.randomize !== false,
          })),
        );
      } catch (e) {
        if (!dead) onError(e instanceof Error ? e.message : "не загрузилось");
      }
    })();
    return () => {
      dead = true;
    };
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
      const startParsed = new Date(form.event_start);
      const startIso = Number.isNaN(startParsed.getTime())
        ? new Date(Date.now()).toISOString()
        : startParsed.toISOString();
      await adminFetch("/admin/settings", "PATCH", {
        event_name: form.event_name,
        event_start: startIso,
        event_end: endIso,
        event_min_deposit: Math.max(50, Number(form.event_min_deposit) || 50),
        dummy_tick_minutes: Math.max(0.5, Number(form.dummy_tick_minutes) || 1),
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
      });
      onStatus("Параметры чемпионата сохранены");
    } catch (err) {
      onError(err instanceof Error ? err.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  async function saveTop() {
    setBusy("top");
    onError("");
    try {
      await adminFetch("/admin/showcase", "PUT", {
        rows: top.map((r) => ({
          place: r.place,
          name: r.name,
          dep: Number(r.dep),
          turn: Number(r.turn),
          balance: Number(r.balance),
          pnl: Number(r.pnl),
          return_pct: Number(r.return_pct),
          uid: r.uid || null,
          randomize: r.randomize !== false,
        })),
      });
      onStatus("Топ-10 сохранён");
    } catch (err) {
      onError(err instanceof Error ? err.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  function patchRow(place: number, patch: Partial<ShowcaseRow>) {
    setTop((prev) => prev.map((r) => (r.place === place ? { ...r, ...patch } : r)));
  }

  const intervalSec = Math.round((Number(form.dummy_tick_minutes) || 1) * 60);

  return (
    <>
      <form className="adm-card" onSubmit={(e) => void saveSettings(e)}>
        <div className="adm-card-header">
          <div className="adm-card-title">Параметры чемпионата</div>
          <span className="adm-badge">UTC+2</span>
        </div>
        <div className="adm-form-row">
          <label className="adm-field">
            Название
            <input
              className="adm-input"
              value={form.event_name}
              onChange={(e) => setForm({ ...form, event_name: e.target.value })}
            />
          </label>
          <label className="adm-field">
            Мин. деп сезона, $
            <input
              className="adm-input"
              type="number"
              min={50}
              value={form.event_min_deposit}
              onChange={(e) => setForm({ ...form, event_min_deposit: Number(e.target.value) })}
            />
            <span className="adm-hint">Строго от $50. Ниже — вне рейтинга.</span>
          </label>
        </div>
        <div className="adm-form-row">
          <label className="adm-field">
            Начало таймера
            <input
              className="adm-input"
              type="datetime-local"
              value={toLocalInput(form.event_start)}
              onChange={(e) => setForm({ ...form, event_start: e.target.value })}
            />
          </label>
          <label className="adm-field">
            Конец чемпионата
            <input
              className="adm-input"
              type="datetime-local"
              value={toLocalInput(form.event_end)}
              onChange={(e) => setForm({ ...form, event_end: e.target.value })}
            />
          </label>
        </div>
        <div className="adm-form-row">
          <label className="adm-field">
            Telegram-канал
            <input
              className="adm-input"
              value={form.telegram_channel_url}
              onChange={(e) => setForm({ ...form, telegram_channel_url: e.target.value })}
            />
          </label>
          <label className="adm-field">
            Ссылка Rami
            <input
              className="adm-input"
              value={form.rami_url}
              onChange={(e) => setForm({ ...form, rami_url: e.target.value })}
            />
          </label>
        </div>

        <div className="adm-rand">
          <h3>Рандомизация Топ-10</h3>
          <label className="adm-field">
            Интервал (минуты)
            <input
              className="adm-input"
              type="number"
              min={0.5}
              step={0.5}
              value={form.dummy_tick_minutes}
              onChange={(e) => setForm({ ...form, dummy_tick_minutes: Number(e.target.value) })}
            />
          </label>
          <div className="adm-interval">
            <div className="adm-interval-label">Текущий интервал</div>
            <div className="adm-interval-value">{form.dummy_tick_minutes} мин</div>
            <div className="adm-interval-sec">{intervalSec} секунд</div>
          </div>
          <div className="adm-presets">
            {[0.5, 1, 5, 10, 30].map((m) => (
              <button
                key={m}
                type="button"
                className="adm-btn ghost sm"
                onClick={() => setForm({ ...form, dummy_tick_minutes: m })}
              >
                {m < 1 ? "30 сек" : `${m} мин`}
              </button>
            ))}
          </div>
        </div>

        <div className="adm-card-header" style={{ marginTop: 24 }}>
          <div className="adm-card-title">Призовой фонд</div>
        </div>
        <label className="adm-field">
          Общий пул, $
          <input
            className="adm-input"
            type="number"
            value={form.prize_pool}
            onChange={(e) => setForm({ ...form, prize_pool: Number(e.target.value) })}
          />
        </label>
        <div className="adm-prize-grid">
          {form.prize_table.map((p, i) => (
            <div className="adm-prize-card" key={i}>
              <input
                className="adm-input"
                value={p.place}
                onChange={(e) => {
                  const prize_table = form.prize_table.slice();
                  prize_table[i] = { ...p, place: e.target.value };
                  setForm({ ...form, prize_table });
                }}
              />
              <input
                className="adm-prize-input"
                type="number"
                value={p.amount}
                onChange={(e) => {
                  const prize_table = form.prize_table.slice();
                  prize_table[i] = { ...p, amount: Number(e.target.value) };
                  setForm({ ...form, prize_table });
                }}
              />
              <input
                className="adm-input"
                placeholder="суффикс"
                value={p.suffix || ""}
                onChange={(e) => {
                  const prize_table = form.prize_table.slice();
                  prize_table[i] = { ...p, suffix: e.target.value };
                  setForm({ ...form, prize_table });
                }}
              />
            </div>
          ))}
        </div>
        <label className="adm-field">
          Правила (по строке)
          <textarea
            className="adm-input"
            rows={7}
            value={form.event_rules}
            onChange={(e) => setForm({ ...form, event_rules: e.target.value })}
          />
        </label>
        <button className="adm-btn success" type="submit" disabled={busy === "set"}>
          {busy === "set" ? "Сохраняем…" : "Сохранить параметры"}
        </button>
      </form>

      <div className="adm-card">
        <div className="adm-card-header">
          <div>
            <div className="adm-card-title">Редактор Топ-10</div>
            <p className="adm-hint">Переключатель рандома + карандаш для ручной правки. В рейтинг сезона — деп с начала таймера.</p>
          </div>
          <button className="adm-btn success" type="button" onClick={() => void saveTop()} disabled={busy === "top"}>
            {busy === "top" ? "Сохраняем…" : "Сохранить топ-10"}
          </button>
        </div>
        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr>
                <th>Место</th>
                <th>Имя</th>
                <th>Депозит</th>
                <th>Оборот</th>
                <th>Прибыль</th>
                <th>Рандом</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {top.map((row) => (
                <tr key={row.place}>
                  <td className={`rank-cell${row.place <= 3 ? ` rank-${row.place}` : ""}`}>{row.place}</td>
                  <td className="name-cell">{row.name}</td>
                  <td>{money(row.dep)}</td>
                  <td>{money(row.turn)}</td>
                  <td className={row.pnl >= 0 ? "profit-cell" : "loss-cell"}>{money(row.pnl)}</td>
                  <td>
                    <button
                      type="button"
                      className={`toggle-switch${row.randomize ? " active" : ""}`}
                      aria-label="рандомизация"
                      onClick={() => patchRow(row.place, { randomize: !row.randomize })}
                    />
                    <span className={`status-badge ${row.randomize ? "status-random" : "status-active"}`}>
                      {row.randomize ? "ВКЛ" : "Выкл"}
                    </span>
                  </td>
                  <td>
                    <button type="button" className="adm-btn ghost icon" onClick={() => setEdit({ ...row })}>
                      ✏️
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {edit ? (
        <div className="adm-modal-overlay active" onClick={() => setEdit(null)}>
          <div className="adm-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Редактирование лида #{edit.place}</h3>
            <div className="adm-form-row">
              <label className="adm-field">
                Имя
                <input
                  className="adm-input"
                  value={edit.name}
                  onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                />
              </label>
              <label className="adm-field">
                Депозит $
                <input
                  className="adm-input"
                  type="number"
                  value={edit.dep}
                  onChange={(e) => setEdit({ ...edit, dep: Number(e.target.value) })}
                />
              </label>
            </div>
            <div className="adm-form-row">
              <label className="adm-field">
                Оборот $
                <input
                  className="adm-input"
                  type="number"
                  value={edit.turn}
                  onChange={(e) => setEdit({ ...edit, turn: Number(e.target.value) })}
                />
              </label>
              <label className="adm-field">
                Баланс $
                <input
                  className="adm-input"
                  type="number"
                  value={edit.balance}
                  onChange={(e) => setEdit({ ...edit, balance: Number(e.target.value) })}
                />
              </label>
            </div>
            <div className="adm-form-row">
              <label className="adm-field">
                Прибыль $
                <input
                  className="adm-input"
                  type="number"
                  value={edit.pnl}
                  onChange={(e) => setEdit({ ...edit, pnl: Number(e.target.value) })}
                />
              </label>
              <label className="adm-field">
                Доходность %
                <input
                  className="adm-input"
                  type="number"
                  step={0.1}
                  value={edit.return_pct}
                  onChange={(e) => setEdit({ ...edit, return_pct: Number(e.target.value) })}
                />
              </label>
            </div>
            <div className="adm-modal-actions">
              <button type="button" className="adm-btn ghost" onClick={() => setEdit(null)}>
                Отмена
              </button>
              <button
                type="button"
                className="adm-btn success"
                onClick={() => {
                  patchRow(edit.place, edit);
                  setEdit(null);
                }}
              >
                Применить
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
