import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "IB CUP — чемпионат по трейдингу",
  description: "Дневной чемпионат IvanBots среди трейдеров Pocket Option. Dubai time.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&family=Syne:wght@600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <Nav />
        {children}
        <footer className="footer wrap">
          IB CUP · сутки по Dubai (UTC+4) · рейтинг строится по снимкам баланса Partners API
        </footer>
      </body>
    </html>
  );
}
