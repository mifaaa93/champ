"use client";

import { useEffect, useMemo, useState } from "react";

type PrizeRow = { place: string; amount: number; suffix?: string };
type BoardKey = "A" | "B";

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
  prize_yield: number[];
  prize_loss_pct: number[];
  loss_comp_cap: number;
  prize_places: number;
  show_nomination_a: boolean;
  show_nomination_b: boolean;
  settings_version: number;
};

export type EventSection = "top" | "prizes" | "params";

function toChampInput(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const shifted = new Date(d.getTime() + 2 * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}T${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}`;
}

function fromChampInput(value: string) {
  if (!value) return "";
  const [date, time] = value.split("T");
  if (!date || !time) return "";
  const parsed = new Date(`${date}T${time}:00+02:00`);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString();
}

function prizeLineTotal(row: PrizeRow) {
  const amount = Number(row.amount || 0);
  if ((row.suffix || "").trim() === "каждое") {
    const match = String(row.place || "").match(/(\d+)\s*[–-]\s*(\d+)/);
    if (match) {
      const count = Number(match[2]) - Number(match[1]) + 1;
      if (count > 0) return amount * count;
    }
  }
  return amount;
}

function money(n: number) {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.round(Math.abs(n)).toLocaleString("en-US")}`;
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

function placeClass(i: number) {
  if (i === 0) return "gold";
  if (i === 1) return "silver";
  if (i === 2) return "bronze";
  return "default";
}

function packRows(rows: ShowcaseRow[]) {
  const byPlace = new Map(rows.map((r) => [r.place, r]));
  return Array.from({ length: 10 }, (_, i) => {
    const place = i + 1;
    const row = byPlace.get(place);
    return row ? { ...emptyRow(place), ...row, place, randomize: row.randomize !== false } : emptyRow(place);
  });
}

function visibilityText(showA: boolean, showB: boolean) {
  if (showA && showB) return "Показывать оба топа с переключением вкладок";
  if (showA) return "Показывать только номинацию A (доходность)";
  if (showB) return "Показывать только номинацию B (потери)";
  return "Оба топа выключены — на сайте останутся оба, с вкладками";
}

function intervalLabel(minutes: number) {
  const m = Number(minutes) || 1;
  const seconds = Math.round(m * 60);
  if (m < 1) return `${seconds} секунд`;
  if (m === 1) return "1 минута";
  if (m < 5) return `${m} минуты`;
  return `${m} минут`;
}

export function EventPanel({
  adminFetch,
  onStatus,
  onError,
  onVersion,
  section,
}: {
  adminFetch: (path: string, method?: string, body?: unknown) => Promise<unknown>;
  onStatus: (s: string) => void;
  onError: (s: string) => void;
  onVersion?: (version: number) => void;
  section: EventSection;
}) {
  const [form, setForm] = useState<EventForm | null>(null);
  const [tops, setTops] = useState<Record<BoardKey, ShowcaseRow[]>>({ A: [], B: [] });
  const [board, setBoard] = useState<BoardKey>("A");
  const [edit, setEdit] = useState<ShowcaseRow | null>(null);
  const [busy, setBusy] = useState("");
  const [addUid, setAddUid] = useState("");

  useEffect(() => {
    let dead = false;
    void (async () => {
      try {
        const s = (await adminFetch("/admin/settings")) as Record<string, unknown>;
        const sc = (await adminFetch("/admin/showcase")) as {
          rows: ShowcaseRow[];
          boards?: { A?: ShowcaseRow[]; B?: ShowcaseRow[] };
        };
        if (dead) return;
        const prize_places = Number(s.prize_places || 3);
        const prize_yield = ((s.prize_yield as number[]) || []).slice();
        const prize_loss_pct = ((s.prize_loss_pct as number[]) || []).slice();
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
          prize_places,
          prize_yield,
          prize_loss_pct,
          loss_comp_cap: Number(s.loss_comp_cap || 0),
          show_nomination_a: s.show_nomination_a !== false,
          show_nomination_b: s.show_nomination_b !== false,
          settings_version: Number(s.settings_version || 0),
        });
        const packedA = packRows(sc.boards?.A || sc.rows || []);
        const packedB = packRows(sc.boards?.B || []);
        setTops({ A: packedA, B: packedB });
      } catch (e) {
        if (!dead) onError(e instanceof Error ? e.message : "не загрузилось");
      }
    })();
    return () => {
      dead = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const prizeSum = useMemo(
    () => (form?.prize_table || []).reduce((acc, p) => acc + prizeLineTotal(p), 0),
    [form],
  );
  const remaining = (form?.prize_pool || 0) - prizeSum;

  if (!form) return <p className="note-dim">Загрузка ивента…</p>;

  async function saveSettings() {
    if (!form) return;
    setBusy("set");
    onError("");
    try {
      const version = Number(form.settings_version || 0);
      const body =
        section === "prizes"
          ? {
              settings_version: version,
              prize_pool: Number(form.prize_pool),
              prize_table: form.prize_table.map((p) => ({
                place: p.place,
                amount: Number(p.amount),
                suffix: p.suffix || "",
              })),
              prize_loss_pct: form.prize_loss_pct.map((n) => Number(n)),
              loss_comp_cap: Number(form.loss_comp_cap),
            }
          : {
              settings_version: version,
              event_name: form.event_name,
              event_start: form.event_start,
              event_end: form.event_end,
              event_min_deposit: Math.max(50, Number(form.event_min_deposit) || 50),
              dummy_tick_minutes: Math.max(0.5, Number(form.dummy_tick_minutes) || 1),
              telegram_channel_url: form.telegram_channel_url,
              rami_url: form.rami_url,
              event_rules: form.event_rules
                .split("\n")
                .map((x) => x.trim())
                .filter(Boolean),
              show_nomination_a: form.show_nomination_a,
              show_nomination_b: form.show_nomination_b,
            };
      const saved = (await adminFetch("/admin/settings", "PATCH", body)) as { settings_version?: number };
      if (saved && saved.settings_version != null) {
        const version = Number(saved.settings_version);
        setForm((prev) => (prev ? { ...prev, settings_version: version } : prev));
        onVersion?.(version);
      }
      onStatus(section === "prizes" ? "Призы сохранены" : "Параметры чемпионата сохранены");
    } catch (err) {
      onError(err instanceof Error ? err.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  function rowsPayload(rows: ShowcaseRow[]) {
    return rows.map((r) => ({
      place: r.place,
      name: r.name,
      dep: Number(r.dep),
      turn: Number(r.turn),
      balance: Number(r.balance),
      pnl: Number(r.pnl),
      return_pct: Number(r.return_pct),
      uid: r.uid || null,
      randomize: r.randomize !== false,
    }));
  }

  async function saveTop() {
    setBusy("top");
    onError("");
    try {
      const saved = (await adminFetch("/admin/showcase", "PUT", {
        boards: { A: rowsPayload(tops.A), B: rowsPayload(tops.B) },
      })) as { boards?: { A?: ShowcaseRow[]; B?: ShowcaseRow[] } };
      if (saved.boards) {
        setTops({
          A: packRows(saved.boards.A || tops.A),
          B: packRows(saved.boards.B || tops.B),
        });
      }
      onStatus("Оба топа сохранены");
    } catch (err) {
      onError(err instanceof Error ? err.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  function patchRow(place: number, patch: Partial<ShowcaseRow>) {
    setTops((prev) => ({
      ...prev,
      [board]: prev[board].map((r) => (r.place === place ? { ...r, ...patch } : r)),
    }));
  }

  function patchPrize(i: number, patch: Partial<PrizeRow>) {
    setForm((prev) => {
      if (!prev) return prev;
      const prize_table = prev.prize_table.slice();
      prize_table[i] = { ...prize_table[i], ...patch };
      return { ...prev, prize_table };
    });
  }

  const intervalSec = Math.round((Number(form.dummy_tick_minutes) || 1) * 60);
  const top = tops[board];
  const lossBoard = board === "B";

  if (section === "top") {
    return (
      <>
        <div className="page-header">
          <div>
            <h1 className="page-title">Редактор Топ-10</h1>
            <div className="page-subtitle">🎲 Оба топа настраиваются отдельно, включая рандомизацию каждой строки</div>
          </div>
          <div className="header-actions">
            <button className="btn btn-success" type="button" onClick={() => void saveTop()} disabled={busy === "top"}>
              {busy === "top" ? "Сохраняем…" : "💾 Сохранить оба"}
            </button>
          </div>
        </div>
        <div className="board-switch">
          <button type="button" className={`board-tab${board === "A" ? " active-a" : ""}`} onClick={() => setBoard("A")}>
            Номинация A · доходность %
          </button>
          <button type="button" className={`board-tab${board === "B" ? " active-b" : ""}`} onClick={() => setBoard("B")}>
            Номинация B · потеря $
          </button>
        </div>
        <div className="card">
          <div className="card-header">
            <div className="card-title">{lossBoard ? "📉 Топ-10 потерь" : "📈 Топ-10 доходности"}</div>
            <span className="card-badge badge-live">● Редактируемый</span>
          </div>
          <p className="form-hint" style={{ margin: "0 0 12px" }}>
            {lossBoard
              ? "Рандомизация держит прибыль отрицательной, чтобы строка оставалась в топе потерь."
              : "Рандомизация держит прибыль положительной. Карандаш правит имя, депозит, оборот, прибыль и доходность."}
          </p>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Место</th>
                  <th>UID</th>
                  <th>Имя</th>
                  <th>Депозит</th>
                  <th>Баланс</th>
                  <th>{lossBoard ? "Потеря" : "Прибыль"}</th>
                  <th>Доходность</th>
                  <th>🎲 Рандом</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {top.map((row) => (
                  <tr key={row.place}>
                    <td className={`rank-cell${row.place <= 3 ? ` rank-${row.place}` : ""}`}>{row.place}</td>
                    <td className="uid-cell">{row.uid || "—"}</td>
                    <td className="name-cell">{row.name}</td>
                    <td>{money(row.dep)}</td>
                    <td>{money(row.balance)}</td>
                    <td className={row.pnl >= 0 ? "profit-cell" : "loss-cell"}>{money(row.pnl)}</td>
                    <td className={row.return_pct >= 0 ? "profit-cell" : "loss-cell"}>
                      {row.return_pct >= 0 ? "+" : ""}
                      {row.return_pct.toFixed(1)}%
                    </td>
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
                      <button type="button" className="btn btn-ghost btn-icon" onClick={() => setEdit({ ...row })}>
                        ✏️
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <div className="card-header">
            <div className="card-title">➕ Найти UID в базе</div>
          </div>
          <div className="search-bar">
            <input
              value={addUid}
              onChange={(e) => setAddUid(e.target.value)}
              placeholder="Введите UID лида…"
            />
            <a className="btn btn-primary" href={addUid ? `/trader/${addUid.replace(/\D/g, "")}?from=admin` : "#"}>
              Открыть карточку
            </a>
          </div>
        </div>
        {edit ? (
          <div className="modal-overlay active" onClick={() => setEdit(null)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h3>✏️ Редактирование лида</h3>
              <p>
                Место: <span style={{ color: "var(--neon-cyan)", fontWeight: 700 }}>#{edit.place}</span>
              </p>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Имя</label>
                  <input className="form-input" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">UID</label>
                  <input
                    className="form-input"
                    value={edit.uid ?? ""}
                    onChange={(e) => setEdit({ ...edit, uid: e.target.value ? Number(e.target.value) : null })}
                  />
                  <div className="form-hint">Справочное поле. На сайте эта строка остаётся демо и не привязывается к живому счёту.</div>
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Депозит ($)</label>
                  <input
                    className="form-input"
                    type="number"
                    value={edit.dep}
                    onChange={(e) => setEdit({ ...edit, dep: Number(e.target.value) })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Баланс ($)</label>
                  <input
                    className="form-input"
                    type="number"
                    value={edit.balance}
                    onChange={(e) => setEdit({ ...edit, balance: Number(e.target.value) })}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Оборот ($)</label>
                  <input
                    className="form-input"
                    type="number"
                    value={edit.turn}
                    onChange={(e) => setEdit({ ...edit, turn: Number(e.target.value) })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{lossBoard ? "Прибыль ($), для потерь со знаком −" : "Прибыль ($)"}</label>
                  <input
                    className="form-input"
                    type="number"
                    value={edit.pnl}
                    onChange={(e) => setEdit({ ...edit, pnl: Number(e.target.value) })}
                  />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Доходность (%)</label>
                <input
                  className="form-input"
                  type="number"
                  step={0.1}
                  value={edit.return_pct}
                  onChange={(e) => setEdit({ ...edit, return_pct: Number(e.target.value) })}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setEdit(null)}>
                  Отмена
                </button>
                <button
                  type="button"
                  className="btn btn-success"
                  onClick={() => {
                    patchRow(edit.place, edit);
                    setEdit(null);
                  }}
                >
                  💾 Сохранить
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </>
    );
  }

  if (section === "prizes") {
    return (
      <>
        <div className="page-header">
          <div>
            <h1 className="page-title">💰 Редактор призов</h1>
            <div className="page-subtitle">Настройка призового фонда в долларах</div>
          </div>
          <div className="header-actions">
            <button className="btn btn-success" type="button" onClick={() => void saveSettings()} disabled={busy === "set"}>
              {busy === "set" ? "Сохраняем…" : "💾 Сохранить призы"}
            </button>
          </div>
        </div>
        <div className="card">
          <div className="card-header">
            <div className="card-title">🏆 Призовой фонд чемпионата</div>
            <span className="card-badge badge-live">● Редактируемый</span>
          </div>
          <div className="form-group">
            <label className="form-label">Общий призовой пул ($)</label>
            <input
              className="form-input"
              type="number"
              value={form.prize_pool}
              onChange={(e) => setForm({ ...form, prize_pool: Number(e.target.value) })}
            />
            <div className="form-hint">Общая сумма, которую вы готовы выплатить победителям</div>
          </div>
          <h3 style={{ fontFamily: "Orbitron, sans-serif", fontSize: 16, margin: "25px 0 15px", color: "var(--neon-gold)" }}>
            Распределение призов
          </h3>
          <div className="prize-editor-grid">
            {form.prize_table.map((p, i) => (
              <div className="prize-card" key={i}>
                <input
                  className={`prize-place ${placeClass(i)}`}
                  style={{
                    background: "transparent",
                    border: 0,
                    textAlign: "center",
                    width: "100%",
                    fontFamily: "Orbitron, sans-serif",
                    fontWeight: 700,
                  }}
                  value={p.place}
                  onChange={(e) => patchPrize(i, { place: e.target.value })}
                />
                <input
                  className="prize-input"
                  type="number"
                  value={p.amount}
                  onChange={(e) => patchPrize(i, { amount: Number(e.target.value) })}
                />
                <input
                  className="form-input"
                  placeholder="суффикс"
                  value={p.suffix || ""}
                  onChange={(e) => patchPrize(i, { suffix: e.target.value })}
                />
                <div className="prize-label">{i === 0 ? "Победитель" : `Место ${i + 1}`}</div>
              </div>
            ))}
          </div>
          <div className="prize-total-bar">
            <div className="label">Сумма призов:</div>
            <div className={`total ${prizeSum > form.prize_pool ? "over" : prizeSum < form.prize_pool ? "under" : ""}`}>
              {money(prizeSum)}
            </div>
          </div>
          <div className="prize-total-bar pool-rest">
            <div className="label">Остаток пула:</div>
            <div className="total">{money(remaining)}</div>
          </div>
        </div>
        <div className="card">
          <div className="card-header">
            <div className="card-title">📉 Компенсация потерь (Номинация B)</div>
          </div>
          <div className="form-row-3">
            {form.prize_loss_pct.map((p, i) => (
              <div className="form-group" key={i}>
                <label className="form-label">{i + 1} место — % от убытка</label>
                <input
                  className="form-input"
                  type="number"
                  min={0}
                  max={100}
                  value={p}
                  onChange={(e) => {
                    const prize_loss_pct = form.prize_loss_pct.slice();
                    prize_loss_pct[i] = Number(e.target.value);
                    setForm({ ...form, prize_loss_pct });
                  }}
                />
              </div>
            ))}
          </div>
          <div className="form-group">
            <label className="form-label">Кап компенсации ($)</label>
            <input
              className="form-input"
              type="number"
              min={0}
              value={form.loss_comp_cap}
              onChange={(e) => setForm({ ...form, loss_comp_cap: Number(e.target.value) })}
            />
            <div className="form-hint">Максимальная выплата одному участнику по номинации B</div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">⚙️ Параметры чемпионата</h1>
          <div className="page-subtitle">Длительность, интервалы, видимость топов</div>
        </div>
        <button className="btn btn-success" type="button" onClick={() => void saveSettings()} disabled={busy === "set"}>
          {busy === "set" ? "Сохраняем…" : "💾 Сохранить все"}
        </button>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">⏱️ Длительность и время</div>
          <span className="card-badge badge-live">UTC+2</span>
        </div>
        <div className="form-group">
          <label className="form-label">Название</label>
          <input className="form-input" value={form.event_name} onChange={(e) => setForm({ ...form, event_name: e.target.value })} />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Начало таймера, UTC+2</label>
            <input
              className="form-input"
              type="datetime-local"
              value={toChampInput(form.event_start)}
              onChange={(e) => setForm({ ...form, event_start: fromChampInput(e.target.value) })}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Конец чемпионата, UTC+2</label>
            <input
              className="form-input"
              type="datetime-local"
              value={toChampInput(form.event_end)}
              onChange={(e) => setForm({ ...form, event_end: fromChampInput(e.target.value) })}
            />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Мин. деп сезона, $</label>
            <input
              className="form-input"
              type="number"
              min={50}
              value={form.event_min_deposit}
              onChange={(e) => setForm({ ...form, event_min_deposit: Number(e.target.value) })}
            />
            <div className="form-hint">Строго от $50. Ниже — вне рейтинга.</div>
          </div>
          <div className="form-group">
            <label className="form-label">Часовой пояс</label>
            <input className="form-input" value="UTC+2" readOnly />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Telegram-канал</label>
            <input
              className="form-input"
              value={form.telegram_channel_url}
              onChange={(e) => setForm({ ...form, telegram_channel_url: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Ссылка Rami</label>
            <input className="form-input" value={form.rami_url} onChange={(e) => setForm({ ...form, rami_url: e.target.value })} />
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">Правила (по строке)</label>
          <textarea
            className="form-input"
            rows={7}
            value={form.event_rules}
            onChange={(e) => setForm({ ...form, event_rules: e.target.value })}
          />
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">🎲 Рандомизация Топ-10</div>
          <span className="card-badge badge-live">● Настраиваемый интервал</span>
        </div>
        <div className="randomization-settings">
          <h3>⚡ Интервал обновления данных</h3>
          <div className="form-group">
            <label className="form-label">Интервал рандомизации (минуты)</label>
            <input
              className="form-input"
              type="number"
              min={0.5}
              max={1440}
              step={0.5}
              value={form.dummy_tick_minutes}
              onChange={(e) => setForm({ ...form, dummy_tick_minutes: Number(e.target.value) })}
            />
            <div className="form-hint">Например: 0.5 = 30 секунд, 1 = 1 минута, 5 = 5 минут</div>
          </div>
          <div style={{ marginTop: 20, padding: 20, background: "rgba(0,0,0,0.3)", borderRadius: 10, textAlign: "center" }}>
            <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 10 }}>Текущий интервал:</div>
            <div className="interval-display">{intervalLabel(form.dummy_tick_minutes)}</div>
            <div style={{ fontSize: 14, color: "var(--neon-cyan)" }}>{intervalSec} секунд</div>
          </div>
          <div className="form-group" style={{ marginTop: 20 }}>
            <label className="form-label">Быстрые presets</label>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {[0.5, 1, 5, 10, 30].map((m) => (
                <button key={m} type="button" className="btn btn-ghost btn-sm" onClick={() => setForm({ ...form, dummy_tick_minutes: m })}>
                  {m < 1 ? "30 сек" : `${m} мин`}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">👁️ Видимость топов на сайте</div>
          <span className="card-badge badge-live">● Управляемые дашборды</span>
        </div>
        <div className="visibility-card">
          <h3>Выберите, какие номинации показывать</h3>
          <div className="visibility-row">
            <div className="info">
              <div className="name" style={{ color: "var(--neon-green)" }}>📈 Номинация A</div>
              <div className="desc">Топ по максимальной доходности %</div>
            </div>
            <button
              type="button"
              className={`toggle-switch${form.show_nomination_a ? " active" : ""}`}
              aria-label="номинация A"
              onClick={() => setForm({ ...form, show_nomination_a: !form.show_nomination_a })}
            />
          </div>
          <div className="visibility-row">
            <div className="info">
              <div className="name" style={{ color: "var(--neon-red)" }}>📉 Номинация B</div>
              <div className="desc">Топ по максимальной потере $ (компенсация)</div>
            </div>
            <button
              type="button"
              className={`toggle-switch${form.show_nomination_b ? " active" : ""}`}
              aria-label="номинация B"
              onClick={() => setForm({ ...form, show_nomination_b: !form.show_nomination_b })}
            />
          </div>
          <div className="config-display">
            <div className="label">Текущая конфигурация:</div>
            <div className="value">{visibilityText(form.show_nomination_a, form.show_nomination_b)}</div>
          </div>
        </div>
      </div>
    </>
  );
}
