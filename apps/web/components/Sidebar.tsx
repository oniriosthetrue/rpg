"use client";

// Barre de navigation latérale (repliable sur mobile). Liens vers les 4 domaines.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

const LIENS = [
  { href: "/", label: "Accueil", icone: "🏠" },
  { href: "/chat", label: "Chat", icone: "💬" },
  { href: "/persos", label: "Personnages", icone: "🧝" },
  { href: "/combat", label: "Combat", icone: "⚔️" },
  { href: "/campagne", label: "Campagne", icone: "📜" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [ouvert, setOuvert] = useState(false);

  async function deconnexion() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/connexion");
    router.refresh();
  }

  return (
    <>
      {/* Barre supérieure (mobile uniquement) */}
      <div className="md:hidden flex items-center gap-2 px-3 py-2 border-b border-white/10 bg-black/30">
        <button
          onClick={() => setOuvert((o) => !o)}
          className="text-or text-xl leading-none"
          aria-label="Menu"
        >
          ☰
        </button>
        <span className="font-bold text-or">MJ D&amp;D</span>
      </div>

      {/* Volet latéral */}
      <aside
        className={`${
          ouvert ? "block" : "hidden"
        } md:block w-full md:w-56 shrink-0 border-b md:border-b-0 md:border-r border-white/10 bg-black/20`}
      >
        <div className="hidden md:block px-4 py-3 font-bold text-or">
          MJ D&amp;D
        </div>
        <nav className="flex md:flex-col gap-1 p-2">
          {LIENS.map((l) => {
            const actif =
              l.href === "/"
                ? pathname === "/"
                : pathname?.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOuvert(false)}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
                  actif
                    ? "bg-or/20 text-or"
                    : "text-parchemin/70 hover:bg-white/5 hover:text-parchemin"
                }`}
              >
                <span>{l.icone}</span>
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-2 border-t border-white/10">
          <button
            onClick={deconnexion}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-parchemin/70 hover:bg-white/5 hover:text-parchemin w-full"
          >
            <span>🚪</span>
            Déconnexion
          </button>
        </div>
      </aside>
    </>
  );
}
