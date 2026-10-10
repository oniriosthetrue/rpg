"use client";

import { useCallback, useEffect, useState } from "react";
import { jdr, ErreurJdr } from "@/lib/jdr";

// Panneau « fiche de personnage » — rendu du JSON canonique `personnage`
// (contrat §8) + barre d'actions closes (soigner, dégâts, or, objet, sort, XP)
// envoyées en PATCH /api/personnages/{nom}.

type Personnage = {
  nom: string;
  espece: string;
  classe: string;
  historique: string;
  alignement: string;
  niveau: number;
  xp: number;
  carac: Record<string, number>;
  mods: Record<string, number>;
  competences: { nom: string; maitrisee: boolean }[];
  langues: string[];
  equipement: string[];
  sorts: string[];
  bonus_maitrise: number;
  pv: number;
  initiative: number;
  ca: number;
  jets?: { competences?: Record<string, number>; sauvegardes?: Record<string, number> };
  don?: string;
  outils?: string[];
};

const CARACS = ["Force", "Dextérité", "Constitution", "Intelligence", "Sagesse", "Charisme"];

function signe(n: number) {
  return n >= 0 ? `+${n}` : `${n}`;
}

export default function FichePerso({ nom }: { nom: string }) {
  const [p, setP] = useState<Personnage | null>(null);
  const [erreur, setErreur] = useState("");
  const [msg, setMsg] = useState("");
  const [enCours, setEnCours] = useState(false);

  const charger = useCallback(async () => {
    if (!nom) return;
    try {
      const r = await fetch(`/api/jdr/personnages/${encodeURIComponent(nom)}`, {
        cache: "no-store",
      });
      const j = await r.json();
      if (j.ok && j.personnage) {
        setP(j.personnage);
        setErreur("");
      } else {
        setErreur(j.erreur ?? "Fiche introuvable.");
      }
    } catch {
      setErreur("Erreur réseau.");
    }
  }, [nom]);

  useEffect(() => {
    setP(null);
    setMsg("");
    charger();
  }, [charger]);

  const appliquer = useCallback(
    async (action: string, valeur: unknown) => {
      if (!nom || enCours) return;
      setEnCours(true);
      setMsg("");
      try {
        const j = await jdr.patch<{
          modifications?: string[];
          personnage?: Personnage;
        }>(`/personnages/${encodeURIComponent(nom)}`, {
          actions: [{ action, valeur }],
        });
        if (j.personnage) setP(j.personnage);
        setMsg(j.modifications?.join(" · ") ?? "Mis à jour.");
      } catch (e) {
        setMsg(e instanceof ErreurJdr ? e.message : "Erreur inconnue.");
      } finally {
        setEnCours(false);
      }
    },
    [nom, enCours],
  );

  const demander = useCallback(
    (action: string, invite: string, nombre = true) => {
      const t = window.prompt(invite);
      if (t == null || t.trim() === "") return;
      appliquer(action, nombre ? Number(t) : t.trim());
    },
    [appliquer],
  );

  if (!nom)
    return (
      <div className="text-parchemin/50 italic p-4">
        Choisis un personnage pour afficher sa fiche.
      </div>
    );
  if (erreur) return <div className="text-red-400 p-4">{erreur}</div>;
  if (!p) return <div className="text-parchemin/50 p-4">Chargement…</div>;

  return (
    <div className="p-4 space-y-4 text-sm">
      <div>
        <div className="text-2xl font-bold text-or">{p.nom}</div>
        <div className="text-parchemin/60">
          {p.espece} · {p.classe} niv. {p.niveau} · {p.alignement}
        </div>
      </div>

      {/* Barre d'actions closes (PATCH) */}
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => demander("soigner", "PV à soigner ?")}
          disabled={enCours}
          className="rounded bg-emerald-700/60 hover:bg-emerald-700 px-2 py-1 text-xs disabled:opacity-40"
        >
          + PV
        </button>
        <button
          onClick={() => demander("degats", "Dégâts encaissés ?")}
          disabled={enCours}
          className="rounded bg-sang/70 hover:bg-sang px-2 py-1 text-xs disabled:opacity-40"
        >
          − PV
        </button>
        <button
          onClick={() => demander("gagner_xp", "XP à gagner ?")}
          disabled={enCours}
          className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 text-xs disabled:opacity-40"
        >
          + XP
        </button>
        <button
          onClick={() => demander("ajouter_or", "Or (po) à ajouter ?")}
          disabled={enCours}
          className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 text-xs disabled:opacity-40"
        >
          + Or
        </button>
        <button
          onClick={() => demander("ajouter_objet", "Nom de l'objet ?", false)}
          disabled={enCours}
          className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 text-xs disabled:opacity-40"
        >
          + Objet
        </button>
        <button
          onClick={() => demander("apprendre_sort", "Nom du sort ?", false)}
          disabled={enCours}
          className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 text-xs disabled:opacity-40"
        >
          + Sort
        </button>
      </div>
      {msg && <div className="text-xs text-or/80">{msg}</div>}

      <div className="grid grid-cols-4 gap-2 text-center">
        {[
          ["Niveau", p.niveau],
          ["PV", p.pv],
          ["CA", p.ca],
          ["Init", signe(p.initiative)],
        ].map(([l, v]) => (
          <div key={l as string} className="bg-white/5 rounded-lg py-2">
            <div className="text-lg font-bold">{v}</div>
            <div className="text-[10px] uppercase tracking-wide text-parchemin/50">{l}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-6 gap-2 text-center">
        {CARACS.map((c) => (
          <div key={c} className="bg-white/5 rounded-lg py-2">
            <div className="text-[10px] text-parchemin/50">{c.slice(0, 4)}</div>
            <div className="text-lg font-bold">{p.carac[c]}</div>
            <div className="text-xs text-or">{signe(p.mods[c])}</div>
          </div>
        ))}
      </div>

      <section>
        <h2 className="text-xs uppercase tracking-wide text-parchemin/50 border-b border-white/10 pb-1 mb-2">
          Compétences
        </h2>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {p.competences
            .slice()
            .sort((a, b) => Number(b.maitrisee) - Number(a.maitrisee))
            .map((c) => (
              <span key={c.nom} className={c.maitrisee ? "text-or" : "text-parchemin/70"}>
                {c.maitrisee ? "● " : "○ "}
                {c.nom}
              </span>
            ))}
        </div>
      </section>

      {p.sorts?.length > 0 && (
        <section>
          <h2 className="text-xs uppercase tracking-wide text-parchemin/50 border-b border-white/10 pb-1 mb-2">
            Sorts
          </h2>
          <div className="flex flex-wrap gap-2">
            {p.sorts.map((s) => (
              <span key={s} className="bg-white/5 rounded px-2 py-0.5">
                {s}
              </span>
            ))}
          </div>
        </section>
      )}

      {p.equipement?.length > 0 && (
        <section>
          <h2 className="text-xs uppercase tracking-wide text-parchemin/50 border-b border-white/10 pb-1 mb-2">
            Équipement
          </h2>
          <ul className="list-disc pl-5 text-parchemin/80">
            {p.equipement.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
