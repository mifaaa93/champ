export type TgRow = {
  place?: number;
  uid: number;
  nickname?: string;
  return_pct?: number;
  pnl?: number;
  prize_amount?: number;
};

export type TgContext = {
  day: string;
  time: string;
  site: string;
  hourly_yield: TgRow[];
  hourly_loss: TgRow[];
  final_source: string;
  final_yield: TgRow[];
  final_loss: TgRow[];
};

const TG_TAGS = new Set([
  "b",
  "strong",
  "i",
  "em",
  "u",
  "ins",
  "s",
  "strike",
  "del",
  "code",
  "pre",
  "a",
  "span",
  "tg-spoiler",
  "blockquote",
]);

function fill(tpl: string, vars: Record<string, string | number>) {
  if (!tpl) return "";
  return tpl.replace(/\{(\w+)\}/g, (_, key: string) =>
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : `{${key}}`
  );
}

function esc(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function fmtPct(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function fmtMoney(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}

function rowVars(place: number, row: TgRow) {
  const uid = row.uid;
  const name = esc(String(row.nickname || uid));
  return {
    place,
    uid,
    name,
    pct: fmtPct(Number(row.return_pct || 0)),
    pnl: fmtMoney(Number(row.pnl || 0)),
    prize: fmtMoney(Number(row.prize_amount || 0)),
  };
}

export type TgTemplates = {
  tg_hourly_header: string;
  tg_yield_title: string;
  tg_yield_row: string;
  tg_yield_empty: string;
  tg_loss_title: string;
  tg_loss_row: string;
  tg_loss_empty: string;
  tg_footer: string;
  tg_final_header: string;
  tg_final_yield_row: string;
  tg_final_loss_row: string;
};

export function buildHourly(ctx: TgContext, t: TgTemplates) {
  const common = { day: ctx.day, time: ctx.time, site: esc(ctx.site) };
  const lines = [fill(t.tg_hourly_header, common), "", fill(t.tg_yield_title, common)];
  if (!ctx.hourly_yield.length) lines.push(fill(t.tg_yield_empty, common));
  ctx.hourly_yield.forEach((r, i) => lines.push(fill(t.tg_yield_row, { ...common, ...rowVars(i + 1, r) })));
  lines.push("", fill(t.tg_loss_title, common));
  if (!ctx.hourly_loss.length) lines.push(fill(t.tg_loss_empty, common));
  ctx.hourly_loss.forEach((r, i) => lines.push(fill(t.tg_loss_row, { ...common, ...rowVars(i + 1, r) })));
  const footer = fill(t.tg_footer, common);
  if (footer.trim()) lines.push("", footer);
  return lines.join("\n");
}

export function buildFinal(ctx: TgContext, t: TgTemplates) {
  const archive = ctx.site ? `${ctx.site}/archive/${ctx.day}` : "";
  const common = { day: ctx.day, time: "", site: esc(archive) };
  const lines = [fill(t.tg_final_header, common), "", fill(t.tg_yield_title, common)];
  (ctx.final_yield || []).forEach((r) =>
    lines.push(fill(t.tg_final_yield_row, { ...common, ...rowVars(r.place || 0, r) }))
  );
  lines.push("", fill(t.tg_loss_title, common));
  (ctx.final_loss || []).forEach((r) =>
    lines.push(fill(t.tg_final_loss_row, { ...common, ...rowVars(r.place || 0, r) }))
  );
  const footer = fill(t.tg_footer, common);
  if (footer.trim()) lines.push("", footer);
  return lines.join("\n");
}

export function validateTelegramHtml(text: string): string[] {
  const errors: string[] = [];
  if (text.length > 4096) errors.push("Сообщение длиннее 4096 символов — Telegram его не примет");
  const stack: string[] = [];
  const tagRe = /<\/?([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^>]*)?>/g;
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === "&") {
      if (!/^&(?:#x[0-9a-fA-F]+|#\d+|[a-zA-Z][a-zA-Z0-9]+);/.test(text.slice(i))) {
        errors.push("Символ & нужно писать как &amp;");
      }
      const m = text.slice(i).match(/^&(?:#x[0-9a-fA-F]+|#\d+|[a-zA-Z][a-zA-Z0-9]+);/);
      i += m ? m[0].length : 1;
      continue;
    }
    if (ch === ">") {
      errors.push("Символ > вне тега нужно писать как &gt;");
      i += 1;
      continue;
    }
    if (ch !== "<") {
      i += 1;
      continue;
    }
    const slice = text.slice(i);
    const m = slice.match(/^<\/?([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^>]*)?>/);
    if (!m) {
      errors.push("Символ < вне тега нужно писать как &lt;. Теги вроде <br> Telegram не понимает.");
      i += 1;
      continue;
    }
    const closing = m[0].startsWith("</");
    const name = m[1].toLowerCase();
    i += m[0].length;
    if (name === "br" || name === "hr" || name === "img") {
      errors.push(`Тег <${name}> в Telegram нельзя. Для новой строки просто нажми Enter.`);
      continue;
    }
    if (!TG_TAGS.has(name)) {
      errors.push(`Тег <${name}> Telegram не понимает. Можно: b, i, u, s, code, pre, a.`);
      continue;
    }
    if (closing) {
      if (!stack.length) errors.push(`Лишний закрывающий </${name}>`);
      else if (stack[stack.length - 1] !== name) errors.push(`Сначала закрой <${stack[stack.length - 1]}>, а не </${name}>`);
      else stack.pop();
    } else {
      stack.push(name);
    }
  }
  for (const open of stack) errors.push(`Не закрыт тег <${open}>`);
  return [...new Set(errors)];
}

export function toPreviewHtml(text: string) {
  let out = "";
  let i = 0;
  while (i < text.length) {
    if (text[i] === "\n") {
      out += "<br>";
      i += 1;
      continue;
    }
    if (text[i] === "<") {
      const m = text.slice(i).match(/^<\/?([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?>/);
      if (m && TG_TAGS.has(m[1].toLowerCase())) {
        const name = m[1].toLowerCase();
        const closing = m[0].startsWith("</");
        if (closing) out += `</${name}>`;
        else if (name === "a") {
          const href = (m[2] || "").match(/href\s*=\s*("([^"]*)"|'([^']*)')/);
          out += `<a href="${esc(href?.[2] || href?.[3] || "")}">`;
        } else out += `<${name}>`;
        i += m[0].length;
        continue;
      }
    }
    out += esc(text[i]);
    i += 1;
  }
  return out;
}
