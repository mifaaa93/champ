const USER_RE = /^[A-Za-z0-9_]{5,32}$/;

export function normalizeTelegram(raw: string): string {
  let value = raw.trim();
  if (!value) return "";
  value = value.split("?")[0].split("#")[0].trim().replace(/^\/+|\/+$/g, "");
  value = value.replace(/^(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\//i, "");
  value = value.replace(/^\/+|\/+$/g, "");
  if (value.toLowerCase().startsWith("s/")) value = value.slice(2);
  return value.replace(/^@/, "").split("/")[0].trim();
}

export function telegramError(raw: string, required: boolean): string {
  const user = normalizeTelegram(raw);
  if (!user) {
    return required ? "Введи Telegram: ссылка, @username или username" : "";
  }
  if (!USER_RE.test(user)) {
    return "Telegram: ссылка t.me, @username или username из 5–32 символов";
  }
  return "";
}
