"use client";

// Page « Combat » : liste des rencontres, ouverture (PJ + monstres saisis),
// et tableau de rencontre (initiative, jets, dégâts, tours).

import { useCallback, useEffect, useState } from "react";
import { usePerso } from "@/components/PersoContext";
import { jdr, ErreurJdr } from "@/lib/jdr";

type Combattant = {
  cle: string;
  nom: string;
  camp: string;
  initiative: number;
  pv: number;
  pv_max: number;
  ca: number;
  conditions: string[];
  vivant: boolean;
};
type Etat = {
  id: string;
  titre: string;
  active: boolean;
  tour: number;
  finie: boolean;
  actif: string | null;
  ordre: Combattant[];
};
type Resume = {
  id: string;
  titre: string;
  active: boolean;
  tour: number;
  nb_combattants: number;
};

export default function PageCombat() {
  const { personnages } = usePerso();
  const [liste, setListe] = useState<Resume[]>([]);
  const [id, setId] = useState("");
  const [etat, setEtat] = useState<Etat | null>(null);
  const [erreur, setErreur] = useState("");
  const [log, setLog] = useState("");

  const chargerListe = useCallback(async () => {
    try {
      const j = await jdr.get<{ rencontres: Resume[] }>("/combat");
      setListe(j.rencontres);
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur liste.");
    }
  }, []);

  const chargerEtat = useCallback(async (rencontreId: string) => {
    try {
      const j = await jdr.get<Etat>(`/combat/${encodeURIComponent(rencontreId)}`);
      setEtat(j);
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur état.");
    }
  }, []);

  useEffect(() => {
    chargerListe();
  }, [chargerListe]);

  useEffect(() => {
    if (id) chargerEtat(id);
    else setEtat(null);
  }, [id, chargerEtat]);

  const action = useCallback(
    async (fn: () => Promise<unknown>, message = "") => {
      setErreur("");
      try {
        await fn();
        if (id) await chargerEtat(id);
        if (message) setLog(message);
      } catch (e) {
        setErreur(e instanceof ErreurJdr ? e.message : "Erreur action.");
      }
    },
    [id, chargerEtat],
  );

  const supprimer = useCallback(
    async (rencontreId: string, titre: string) => {
      if (
        !window.confirm(
          `Supprimer définitivement la rencontre « ${titre || rencontreId} » ?`,
        )
      )
        return;
      setErreur("");
      try {
        await jdr.del(`/combat/${encodeURIComponent(rencontreId)}`);
        if (id === rencontreId) setId("");
        await chargerListe();
      } catch (e) {
        setErreur(e instanceof ErreurJdr ? e.message : "Erreur de suppression.");
      }
    },
    [id, chargerListe],
  );

  return (
    <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
      {/* Colonne gauche : liste + ouverture */}
      <section className="w-full md:w-80 shrink-0 overflow-y-auto border-b md:border-b-0 md:border-r border-white/10 bg-black/10">
        <div className="p-3 border-b border-white/10 font-bold text-or">
          Rencontres
        </div>
        <div className="p-2 space-y-1">
          {liste.length === 0 && (
            <p className="text-parchemin/40 italic text-sm p-2">
              Aucune rencontre. Ouvre-en une ci-dessous.
            </p>
          )}
          {liste.map((r) => (
            <div
              key={r.id}
              onClick={() => setId(r.id)}
              className={`group flex items-center gap-2 w-full text-left rounded-lg px-3 py-2 text-sm cursor-pointer ${
                r.id === id ? "bg-or/20 text-or" : "hover:bg-white/5"
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="truncate">{r.titre || r.id}</div>
                <div className="text-[11px] text-parchemin/50">
                  {r.active ? `tour ${r.tour}` : "clôturée"} · {r.nb_combattants}{" "}
                  combattants
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  supprimer(r.id, r.titre);
                }}
                title="Supprimer la rencontre"
                aria-label="Supprimer la rencontre"
                className="shrink-0 p-1 -m-1 text-parchemin/50 hover:text-red-400 active:text-red-400"
              >
                🗑
              </button>
            </div>
          ))}
        </div>
        <FormulaireOuverture
          personnages={personnages.map((p) => p.nom)}
          onOuvert={(nouvelId) => {
            chargerListe();
            setId(nouvelId);
          }}
        />
      </section>

      {/* Colonne droite : tableau de rencontre */}
      <section className="flex-1 overflow-y-auto p-4">
        {erreur && <div className="text-red-400 text-sm mb-2">{erreur}</div>}
        {log && <div className="text-or/80 text-sm mb-2">{log}</div>}
        {!etat ? (
          <p className="text-parchemin/40 italic">
            Sélectionne ou ouvre une rencontre.
          </p>
        ) : (
          <Tableau
            etat={etat}
            onAction={action}
            onCLOTURE={async () => {
              await action(
                () => jdr.post(`/combat/${encodeURIComponent(id)}/cloturer`),
                "Rencontre clôturée.",
              );
              chargerListe();
            }}
          />
        )}
      </section>
    </div>
  );
}

function Tableau({
  etat,
  onAction,
  onCLOTURE,
}: {
  etat: Etat;
  onAction: (fn: () => Promise<unknown>, msg?: string) => Promise<void>;
  onCLOTURE: () => Promise<void>;
}) {
  const [cible, setCible] = useState("");

  const jetMonstre = (attaquant: string) => {
    const c = cible || etat.ordre.find((x) => x.camp === "pj" && x.vivant)?.cle;
    if (!c) return;
    onAction(
      () => jdr.post(`/combat/${encodeURIComponent(etat.id)}/jet-monstre`, {
        attaquant,
        cible: c,
      }),
      `Jet du monstre contre ${nomDe(etat, c)}.`,
    );
  };

  const jetJoueur = (attaquant: string) => {
    const c = cible || etat.ordre.find((x) => x.camp === "monstre" && x.vivant)?.cle;
    if (!c) return;
    const d20 = window.prompt("Ton d20 (1-20) ?");
    if (d20 == null) return;
    onAction(
      () => jdr.post(`/combat/${encodeURIComponent(etat.id)}/jet-joueur`, {
        attaquant,
        cible: c,
        de_attaque: Number(d20),
      }),
      `Jet du joueur contre ${nomDe(etat, c)}.`,
    );
  };

  const patch = (cle: string, action: string) => {
    const v = window.prompt(
      action === "condition" ? "Condition ?" : "Valeur ?",
    );
    if (v == null || v.trim() === "") return;
    onAction(
      () => jdr.patch(`/combat/${encodeURIComponent(etat.id)}`, {
        cle,
        action,
        valeur: action === "condition" ? v.trim() : Number(v),
      }),
      `${action} sur ${nomDe(etat, cle)}.`,
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-bold text-or">{etat.titre || etat.id}</h2>
        <span className="text-sm text-parchemin/60">Tour {etat.tour}</span>
        {etat.active && (
          <button
            onClick={onCLOTURE}
            className="ml-auto rounded bg-sang/70 hover:bg-sang px-3 py-1 text-xs"
          >
            Clôturer
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 text-sm">
        <label className="text-parchemin/60">Cible :</label>
        <select
          value={cible}
          onChange={(e) => setCible(e.target.value)}
          className="bg-white/5 rounded px-2 py-1 outline-none"
        >
          <option value="">(auto)</option>
          {etat.ordre
            .filter((c) => c.vivant)
            .map((c) => (
              <option key={c.cle} value={c.cle}>
                {c.nom} ({c.camp})
              </option>
            ))}
        </select>
        {etat.active && (
          <button
            onClick={() =>
              onAction(
                () => jdr.post(`/combat/${encodeURIComponent(etat.id)}/tour-suivant`),
                "Tour suivant.",
              )
            }
            className="ml-auto rounded bg-or/80 hover:bg-or text-encre px-3 py-1 text-xs font-semibold"
          >
            ▶ Tour suivant
          </button>
        )}
      </div>

      <div className="space-y-2">
        {etat.ordre.map((c) => {
          const actif = c.cle === etat.actif;
          return (
            <div
              key={c.cle}
              className={`rounded-lg border p-3 ${
                actif ? "border-or bg-or/10" : "border-white/10 bg-white/5"
              } ${c.vivant ? "" : "opacity-40"}`}
            >
              <div className="flex items-center gap-2">
                <span className="w-8 text-center text-parchemin/50">
                  {c.initiative}
                </span>
                <span className="font-semibold">{c.nom}</span>
                <span className="text-xs text-parchemin/50">
                  {c.camp} · CA {c.ca} · {c.pv}/{c.pv_max} PV
                </span>
                {actif && <span className="text-xs text-or">◀ actif</span>}
                {c.conditions.length > 0 && (
                  <span className="text-xs text-sang/80">
                    [{c.conditions.join(", ")}]
                  </span>
                )}
              </div>
              {c.vivant && etat.active && (
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  {c.camp === "monstre" ? (
                    <button
                      onClick={() => jetMonstre(c.cle)}
                      className="rounded bg-sang/60 hover:bg-sang px-2 py-1"
                    >
                      Attaque (serveur)
                    </button>
                  ) : (
                    <button
                      onClick={() => jetJoueur(c.cle)}
                      className="rounded bg-emerald-700/60 hover:bg-emerald-700 px-2 py-1"
                    >
                      Attaque (mon d20)
                    </button>
                  )}
                  <button
                    onClick={() => patch(c.cle, "degats")}
                    className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                  >
                    − PV
                  </button>
                  <button
                    onClick={() => patch(c.cle, "soigner")}
                    className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                  >
                    + PV
                  </button>
                  <button
                    onClick={() => patch(c.cle, "condition")}
                    className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                  >
                    Condition
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function nomDe(etat: Etat, cle: string) {
  return etat.ordre.find((c) => c.cle === cle)?.nom ?? cle;
}

function FormulaireOuverture({
  personnages,
  onOuvert,
}: {
  personnages: string[];
  onOuvert: (id: string) => void;
}) {
  const [titre, setTitre] = useState("");
  const [pjSel, setPjSel] = useState<string[]>([]);
  const [monstres, setMonstres] = useState("");
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);

  const ouvrir = useCallback(async () => {
    setErreur("");
    let specs: unknown[];
    try {
      specs = monstres.trim() ? JSON.parse(monstres) : [];
    } catch {
      setErreur("Les monstres doivent être du JSON valide.");
      return;
    }
    const combattants = [
      ...pjSel.map((nom) => ({ type: "pj", nom })),
      ...(specs as unknown[]).map((s) => ({ type: "monstre", ...(s as object) })),
    ];
    if (combattants.length < 2) {
      setErreur("Au moins 2 combattants (PJ + monstres).");
      return;
    }
    setEnCours(true);
    try {
      const j = await jdr.post<{ id: string }>("/combat/ouvrir", {
        titre,
        combattants,
      });
      setPjSel([]);
      setMonstres("");
      setTitre("");
      onOuvert(j.id);
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur ouverture.");
    } finally {
      setEnCours(false);
    }
  }, [titre, pjSel, monstres, onOuvert]);

  return (
    <div className="border-t border-white/10 p-3 space-y-2">
      <div className="font-semibold text-or text-sm">Ouvrir une rencontre</div>
      <input
        value={titre}
        onChange={(e) => setTitre(e.target.value)}
        placeholder="Titre"
        className="w-full bg-white/5 rounded px-2 py-1 text-sm outline-none"
      />
      <div className="text-xs text-parchemin/60">PJ présents :</div>
      <div className="flex flex-wrap gap-1">
        {personnages.map((n) => (
          <button
            key={n}
            onClick={() =>
              setPjSel((s) =>
                s.includes(n) ? s.filter((x) => x !== n) : [...s, n],
              )
            }
            className={`rounded px-2 py-1 text-xs ${
              pjSel.includes(n) ? "bg-or/30 text-or" : "bg-white/10"
            }`}
          >
            {n}
          </button>
        ))}
        {personnages.length === 0 && (
          <span className="text-xs text-parchemin/40">aucun PJ</span>
        )}
      </div>
      <textarea
        value={monstres}
        onChange={(e) => setMonstres(e.target.value)}
        rows={3}
        placeholder='Monstres JSON : [{"nom":"Orc","pv":11,"ca":13,"attaque":5,"degats":"1d12","mod_degats":3,"nb":2}]'
        className="w-full bg-white/5 rounded px-2 py-1 text-xs outline-none font-mono"
      />
      {erreur && <div className="text-red-400 text-xs">{erreur}</div>}
      <button
        onClick={ouvrir}
        disabled={enCours}
        className="rounded-lg bg-or/80 hover:bg-or text-encre text-xs font-semibold px-3 py-1.5 disabled:opacity-40"
      >
        Lancer l&apos;initiative
      </button>
    </div>
  );
}
