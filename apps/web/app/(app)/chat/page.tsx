"use client";

import Chat from "@/components/Chat";
import FichePerso from "@/components/FichePerso";
import { usePerso } from "@/components/PersoContext";

export default function PageChat() {
  const { nom, rafraichir } = usePerso();
  return (
    <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
      <section className="flex-1 min-h-0 overflow-hidden border-b md:border-b-0 md:border-r border-white/10">
        <Chat />
      </section>
      {/* Fiche perso : masquée sur téléphone (le chat prend tout l'écran pour
          jouer). La fiche complète reste accessible via l'onglet « Personnages ». */}
      <aside className="hidden md:block md:w-96 overflow-y-auto bg-black/10">
        <FichePerso key={`${nom}-${rafraichir}`} nom={nom} />
      </aside>
    </div>
  );
}
