import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PO Championship",
  description: "Чемпионат. Рейтинг по депозиту сезона.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=Orbitron:wght@400;700;900&family=Syne:wght@600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
