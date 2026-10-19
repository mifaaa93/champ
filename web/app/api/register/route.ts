import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  // Only the socket-stamping wrapper may supply a trustworthy client address.
  const ip = process.env.WEB_SOCKET_IP_STAMPED === "1"
    ? req.headers.get("x-real-ip") || "unknown"
    : "unknown";
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Некорректный запрос" }, { status: 400 });
  }
  const api = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
  const res = await fetch(`${api}/public/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Real-IP": ip,
    },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
  });
}
