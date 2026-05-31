import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Battlemap Repository",
  description: "A personal library of TTRPG battlemaps.",
  // Keep this personal archive out of search engines (still fully accessible directly).
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link href="/" className="brand">🗺️ Battlemaps</Link>
          <nav>
            <Link href="/">Gallery</Link>
            <Link href="/admin">Admin</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
