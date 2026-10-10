"use client";

// Assistant de création de scénario. Collecte le cadrage (mode guidé/surprise,
// âge du joueur, durée visée, effectif/niveaux, piliers, ton, thème) puis ouvre
// la campagne via POST /api/campagne/ouvrir. Le contenu narratif reste la main
// du MJ/LLM : ici on ne renseigne que la structure de cadrage.

import { useCallback, useState } from "react";
import { jdr, ErreurJdr } from "@/lib/jdr";

type Ouverture = { ok: boolean; type: string; id: string; erreur?: string };

const MODES = [
  { v: "guide", t: "Guidé", d: "On construit la trame ensemble, une décision à la fois." },
  { v: "surprise", t: "Surprise", d: "Le MJ l'invente en secret et ne révèle que l'accroche." },
];
const DUREES = [
  { v: "one-shot", t: "One-shot (1 séance)" },
  { v: "courte", t: "Courte (2-4 séances)" },
  { v: "moyenne", t: "Moyenne (5-10 séances)" },
  { v: "longue", t: "Longue (campagne)" },
];
const PILIERS = [
  { v: "exploration", t: "Exploration" },
  { v: "social", t: "Interaction sociale" },
  { v: "combat", t: "Combat" },
];

const ETAPES = ["mode", "age", "duree", "groupe", "piliers", "ton", "theme"] as const;
type Etape = (typeof ETAPES)[number];

export default function CreationCampagne({
  onOuverte,
  onAnnuler,
}: {
  onOuverte: (id: string) => void;
  onAnnuler: () => void;
}) {
  const [etape, setEtape] = useState<Etape>("mode");
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState("");

  const [mode, setMode] = useState("guide");
  const [age, setAge] = useState("");
  const [duree, setDuree] = useState("");
  const [nbJoueurs, setNbJoueurs] = useState("");
  const [niveaux, setNiveaux] = useState("");
  const [piliers, setPiliers] = useState<string[]>([]);
  const [ton, setTon] = useState("");
  const [titre, setTitre] = useState("");
  const [theme, setTheme] = useState("");

  const idx = ETAPES.indexOf(etape);
  const precedent = () => idx > 0 && setEtape(ETAPES[idx - 1]);
  const suivant = () => idx < ETAPES.length - 1 && setEtape(ETAPES[idx + 1]);

  const basculerPilier = (v: string) =>
    setPiliers((p) => (p.includes(v) ? p.filter((x) => x !== v) : [...p, v]));

  const ouvrir = useCallback(async () => {
    if (enCours) return;
    setErreur("");
    if (!age.trim()) {
      setErreur("L'âge du joueur est obligatoire.");
      setEtape("age");
      return;
    }
    if (!duree) {
      setErreur("La durée visée est obligatoire.");
      setEtape("duree");
      return;
    }
    setEnCours(true);
    try {
      const corps: Record<string, unknown> = {
        mode,
        titre: titre.trim(),
        age_joueur: Number(age) || 0,
        duree,
        nb_joueurs: Number(nbJoueurs) || 0,
        niveaux: niveaux
          .split(",")
          .map((n) => Number(n.trim()))
          .filter((n) => !Number.isNaN(n) && n > 0),
        piliers,
        ton: ton.trim(),
        theme: theme.trim(),
      };
      const j = await jdr.post<Ouverture>("/campagne/ouvrir", corps);
      onOuverte(j.id);
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur à l'ouverture.");
    } finally {
      setEnCours(false);
    }
  }, [enCours, mode, titre, age, duree, nbJoueurs, niveaux, piliers, ton, theme, onOuverte]);

  const titreEtape: Record<Etape, string> = {
    mode: "Quel mode de création ?",
    age: "Quel est l'âge du joueur ?",
    duree: "Quelle durée visée pour la partie ?",
    groupe: "Combien de joueurs, et à quel niveau ?",
    piliers: "Quels piliers privilégier ?",
    ton: "Quel ton souhaites-tu ?",
    theme: "Titre et idée de départ ?",
  };

  return (
    <div className="p-4 space-y-3">
      <div className="text-xs text-parchemin/50">
        Nouvelle campagne · étape {idx + 1}/{ETAPES.length}
      </div>
      <p className="font-semibold text-or">{titreEtape[etape]}</p>

      {etape === "mode" && (
        <div className="flex flex-col gap-1.5">
          {MODES.map((m) => (
            <button
              key={m.v}
              onClick={() => {
                setMode(m.v);
                suivant();
              }}
              className={`rounded-lg px-3 py-2 text-left text-sm ${
                mode === m.v ? "bg-or/20 text-or" : "bg-white/5 hover:bg-white/10"
              }`}
            >
              <div className="font-semibold">{m.t}</div>
              <div className="text-xs text-parchemin/60">{m.d}</div>
            </button>
          ))}
        </div>
      )}

      {etape === "age" && (
        <div className="space-y-2">
          <input
            type="number"
            min={4}
            max={120}
            value={age}
            onChange={(e) => setAge(e.target.value)}
            placeholder="Âge du joueur (obligatoire)"
            className="w-full bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
          />
          <p className="text-xs text-parchemin/50">
            Le MJ adapte le ton et le niveau de violence à cet âge.
          </p>
        </div>
      )}

      {etape === "duree" && (
        <div className="flex flex-col gap-1.5">
          {DUREES.map((d) => (
            <button
              key={d.v}
              onClick={() => {
                setDuree(d.v);
                suivant();
              }}
              className={`rounded-lg px-3 py-2 text-left text-sm ${
                duree === d.v ? "bg-or/20 text-or" : "bg-white/5 hover:bg-white/10"
              }`}
            >
              {d.t}
            </button>
          ))}
        </div>
      )}

      {etape === "groupe" && (
        <div className="space-y-2">
          <input
            type="number"
            min={0}
            value={nbJoueurs}
            onChange={(e) => setNbJoueurs(e.target.value)}
            placeholder="Nombre de joueurs (option)"
            className="w-full bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
          />
          <input
            value={niveaux}
            onChange={(e) => setNiveaux(e.target.value)}
            placeholder="Niveaux des PJ, ex. 3,3,4 (option)"
            className="w-full bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
          />
        </div>
      )}

      {etape === "piliers" && (
        <div className="flex flex-wrap gap-1.5">
          {PILIERS.map((p) => {
            const actif = piliers.includes(p.v);
            return (
              <button
                key={p.v}
                onClick={() => basculerPilier(p.v)}
                className={`rounded px-3 py-1.5 text-sm ${
                  actif ? "bg-or text-encre font-semibold" : "bg-white/10 hover:bg-white/20"
                }`}
              >
                {p.t}
              </button>
            );
          })}
        </div>
      )}

      {etape === "ton" && (
        <input
          value={ton}
          onChange={(e) => setTon(e.target.value)}
          placeholder="ex. sombre, épique, humoristique… (option)"
          className="w-full bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
        />
      )}

      {etape === "theme" && (
        <div className="space-y-2">
          <input
            value={titre}
            onChange={(e) => setTitre(e.target.value)}
            placeholder="Titre du scénario (option)"
            className="w-full bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
          />
          <textarea
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            rows={3}
            placeholder="Une idée de départ, un lieu, une menace… (option)"
            className="w-full bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
          />
        </div>
      )}

      {erreur && <div className="text-red-400 text-sm">{erreur}</div>}

      <div className="flex items-center gap-2 pt-1">
        {idx > 0 && (
          <button
            onClick={precedent}
            disabled={enCours}
            className="rounded bg-white/10 hover:bg-white/20 px-3 py-1.5 text-sm disabled:opacity-40"
          >
            ⬅ Retour
          </button>
        )}
        {etape !== "theme" ? (
          <button
            onClick={suivant}
            disabled={
              enCours ||
              (etape === "age" && !age.trim()) ||
              (etape === "duree" && !duree)
            }
            className="rounded-lg bg-or/80 hover:bg-or text-encre font-semibold px-4 py-1.5 text-sm disabled:opacity-40"
          >
            Suivant
          </button>
        ) : (
          <button
            onClick={ouvrir}
            disabled={enCours}
            className="rounded-lg bg-emerald-700/70 hover:bg-emerald-700 text-white font-semibold px-4 py-1.5 text-sm disabled:opacity-40"
          >
            {enCours ? "…" : "Ouvrir la campagne"}
          </button>
        )}
        <button
          onClick={onAnnuler}
          disabled={enCours}
          className="ml-auto rounded bg-sang/60 hover:bg-sang px-3 py-1.5 text-sm disabled:opacity-40"
        >
          Annuler
        </button>
      </div>
    </div>
  );
}
