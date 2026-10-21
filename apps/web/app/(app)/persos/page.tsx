"use client";

// Page « Personnages » : grille des persos, sélection, suppression, et
// assistant de création guidée.

import { useCallback, useState } from "react";
import CreationWizard from "@/components/CreationWizard";
import FichePerso from "@/components/FichePerso";
import { usePerso } from "@/components/PersoContext";
import { jdr, ErreurJdr } from "@/lib/jdr";

export default function PagePersos() {
  const { personnages, nom, setNom, rafraichir, rechargerListe } = usePerso();
  const [wizard, setWizard] = useState(false);
  const [erreur, setErreur] = useState("");

  const supprimer = useCallback(
    async (n: string) => {
      if (!window.confirm(`Supprimer définitivement « ${n} » ?`)) return;
      setErreur("");
      try {
        await jdr.del(`/personnages/${encodeURIComponent(n)}`);
        if (n === nom) setNom("");
        await rechargerListe();
      } catch (e) {
        setErreur(e instanceof ErreurJdr ? e.message : "Erreur de suppression.");
      }
    },
    [nom, setNom, rechargerListe],
  );

  return (
    <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
      <section className="w-full md:w-80 shrink-0 overflow-y-auto border-b md:border-b-0 md:border-r border-white/10 bg-black/10">
        <div className="p-3 flex items-center gap-2 border-b border-white/10">
          <h2 className="font-bold text-or">Personnages</h2>
          <button
            onClick={() => setWizard((w) => !w)}
            className="ml-auto rounded-lg bg-or/80 hover:bg-or text-encre text-xs font-semibold px-3 py-1.5"
          >
            {wizard ? "Fermer" : "+ Créer"}
          </button>
        </div>

        {wizard && (
          <div className="border-b border-white/10">
            <CreationWizard
              onTermine={() => {
                setWizard(false);
                rechargerListe();
              }}
            />
          </div>
        )}

        {erreur && <div className="px-3 py-2 text-red-400 text-xs">{erreur}</div>}

        <div className="p-2 space-y-1">
          {personnages.length === 0 && !wizard && (
            <p className="text-parchemin/40 italic text-sm p-2">
              Aucun personnage. Clique « + Créer ».
            </p>
          )}
          {personnages.map((p) => (
            <div
              key={p.nom}
              className={`group flex items-center gap-2 rounded-lg px-3 py-2 text-sm cursor-pointer ${
                p.nom === nom ? "bg-or/20 text-or" : "hover:bg-white/5"
              }`}
              onClick={() => setNom(p.nom)}
            >
              <div className="flex-1 min-w-0">
                <div className="truncate">{p.nom}</div>
                <div className="text-[11px] text-parchemin/50 truncate">
                  {p.espece} · {p.classe} niv.{p.niveau}
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  supprimer(p.nom);
                }}
                title="Supprimer"
                aria-label="Supprimer le personnage"
                className="shrink-0 p-1 -m-1 text-parchemin/50 hover:text-red-400 active:text-red-400"
              >
                🗑
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="flex-1 overflow-y-auto">
        <FichePerso key={`${nom}-${rafraichir}`} nom={nom} />
      </section>
    </div>
  );
}
