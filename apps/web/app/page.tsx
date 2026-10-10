"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Chat from "@/components/Chat";
import FichePerso from "@/components/FichePerso";

type Perso = { nom: string; espece: string; classe: string; niveau: number };

export default function Accueil() {
  const [personnages, setPersonnages] = useState<Perso[]>([]);
  const [nom, setNom] = useState("");
  const [rafraichir, setRafraichir] = useState(0);
  // Identifiant de conversation stable sur la session (pour le message_history).
  const chatId = useMemo(
    () => (typeof crypto !== "undefined" ? crypto.randomUUID() : "defaut"),
    [],
  );

  const chargerListe = useCallback(async () => {
    try {
      const r = await fetch("/api/jdr/personnages", { cache: "no-store" });
      const j = await r.json();
      if (j.ok && Array.isArray(j.personnages)) {
        setPersonnages(j.personnages);
        setNom((n) => n || j.personnages[0]?.nom || "");
      }
    } catch {
      /* backend indisponible : liste vide */
    }
  }, []);

  useEffect(() => {
    chargerListe();
  }, [chargerListe]);

  return (
    <main className="h-screen flex flex-col">
      <header className="flex items-center gap-3 px-4 py-2 border-b border-white/10 bg-black/20">
        <h1 className="text-lg font-bold text-or">MJ D&amp;D</h1>
        <select
          value={nom}
          onChange={(e) => setNom(e.target.value)}
          className="bg-white/5 rounded px-2 py-1 text-sm outline-none"
        >
          {personnages.length === 0 && <option value="">(aucun personnage)</option>}
          {personnages.map((p) => (
            <option key={p.nom} value={p.nom}>
              {p.nom} — {p.classe} niv.{p.niveau}
            </option>
          ))}
        </select>
        <button
          onClick={chargerListe}
          className="ml-auto text-xs text-parchemin/60 hover:text-or"
          title="Recharger la liste"
        >
          ↻
        </button>
      </header>

      <div className="flex-1 flex overflow-hidden flex-col md:flex-row">
        <section className="flex-1 overflow-hidden border-r border-white/10">
          <Chat
            chatId={chatId}
            personnage={nom}
            onChangementFiche={() => setRafraichir((n) => n + 1)}
          />
        </section>
        <aside className="w-full md:w-96 overflow-y-auto bg-black/10">
          <FichePerso key={`${nom}-${rafraichir}`} nom={nom} />
        </aside>
      </div>
    </main>
  );
}
