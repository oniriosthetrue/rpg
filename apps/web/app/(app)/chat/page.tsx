"use client";

import Chat from "@/components/Chat";
import FichePerso from "@/components/FichePerso";
import { usePerso } from "@/components/PersoContext";

export default function PageChat() {
  const { nom, rafraichir } = usePerso();
  return (
    <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
      <section className="flex-1 overflow-hidden border-b md:border-b-0 md:border-r border-white/10">
        <Chat />
      </section>
      <aside className="w-full md:w-96 overflow-y-auto bg-black/10">
        <FichePerso key={`${nom}-${rafraichir}`} nom={nom} />
      </aside>
    </div>
  );
}
