import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MJ D&D — Maître de Jeu",
  description: "Maître de Jeu virtuel D&D 5.2.1 (SRD) — app dédiée.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
