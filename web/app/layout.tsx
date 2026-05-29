import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Battlemap Repository",
  description: "A personal library of TTRPG battlemaps.",
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
