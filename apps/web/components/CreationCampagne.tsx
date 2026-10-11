"use client";

// Assistant de création de scénario. Collecte le cadrage (mode guidé/surprise,
// âge du joueur, durée visée, effectif/niveaux, piliers, ton, thème) puis ouvre
// la campagne via POST /api/campagne/ouvrir. Le contenu narratif reste la main
// du MJ/LLM : ici on ne renseigne que la structure de cadrage.

import { useCallback, useState } from "react";
import { jdr, ErreurJdr } from "@/lib/jdr";
import { usePerso } from "./PersoContext";
import { CheckboxLigne } from "./Checkbox";

type Ouverture = {
  ok: boolean;
  type: string;
  id: string;
  erreur?: string;
  inspirations?: Record<string, string[]>;
};

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
  onAnnuler,
}: {
  onAnnuler: () => void;
}) {
  const { personnages } = usePerso();
  const [etape, setEtape] = useState<Etape>("mode");
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState("");

  const [mode, setMode] = useState("guide");
  const [age, setAge] = useState("");
  const [duree, setDuree] = useState("");
  // PJ porteurs du scénario : sélection parmi les fiches existantes. Le scénario
  // sera adapté à ce groupe précis (crochets liés au background, équilibrage,
  // épreuves selon les aptitudes). `niveaux` et `nb_joueurs` en sont dérivés.
  const [pjSel, setPjSel] = useState<string[]>([]);
  const [piliers, setPiliers] = useState<string[]>([]);
  const [ton, setTon] = useState("");
  const [titre, setTitre] = useState("");
  const [theme, setTheme] = useState("");

  const basculerPj = (nom: string) =>
    setPjSel((p) => (p.includes(nom) ? p.filter((x) => x !== nom) : [...p, nom]));

  // En mode surprise, le MJ invente tout en secret : on ne demande ni titre ni
  // idée de départ (l'étape « theme »), qui trahiraient la surprise.
  const etapes: Etape[] =
    mode === "surprise"
      ? ETAPES.filter((e) => e !== "theme")
      : [...ETAPES];
  const idx = etapes.indexOf(etape);
  const estDerniere = etape === etapes[etapes.length - 1];
  const precedent = () => idx > 0 && setEtape(etapes[idx - 1]);
  const suivant = () => idx < etapes.length - 1 && setEtape(etapes[idx + 1]);

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
        pj: pjSel,
        nb_joueurs: pjSel.length,
        niveaux: pjSel
          .map((n) => personnages.find((p) => p.nom === n)?.niveau ?? 1)
          .filter((n) => n > 0),
        piliers,
        ton: ton.trim(),
        theme: theme.trim(),
      };
      const j = await jdr.post<Ouverture>("/campagne/ouvrir", corps);
      // On enchaîne sur le chat, lié à cette campagne, avec une amorce de génération.
      const titreCamp = titre.trim() || "la campagne";
      const groupe = pjSel.length
        ? ` Le scénario est destiné à ce groupe de PJ : ${pjSel.join(
            ", ",
          )}. Charge la fiche de chacun (charger_le_personnage) et adapte-lui le scénario : `
        : "";
      // Graines d'inspiration tirées par le serveur à l'ouverture (variété).
      const LIBELLES: Record<string, string> = {
        crochets: "crochet",
        pnj: "PNJ",
        conflits: "conflit/twist",
        saveurs: "saveur",
      };
      const graines = Object.entries(j.inspirations ?? {})
        .flatMap(([dim, vals]) =>
          (vals ?? []).map((v) => `${LIBELLES[dim] ?? dim} : ${v}`),
        )
        .join(" · ");
      const aideVariete = graines
        ? `GRAINES D'INSPIRATION (à réécrire et tisser avec le cadrage et les PJ, jamais à recopier mot à mot) — ${graines}. Tu peux en piocher d'autres avec tirer_sur_une_table. `
        : "";
      const consigne =
        `Construis le scénario de la campagne « ${titreCamp} » en respectant le ` +
        `cadrage (relis etat_de_la_campagne pour le mode, l'âge, la durée, les piliers, ` +
        `le ton et le conseil_cadrage). ` +
        groupe +
        aideVariete +
        `attache chaque crochet au background d'un PJ (lie_a_pj), équilibre les ` +
        `rencontres sur leurs niveaux, et varie les épreuves selon leurs aptitudes. ` +
        `IMPORTANT : après avoir conçu la trame, PERSISTE-LA avec l'outil ` +
        `ecrire_le_scenario(campagne_id, …) (titre, synopsis, accroche, enjeux, pnj, ` +
        `crochets, defis, lieux, blocs) — sinon elle reste dans la conversation et la ` +
        `campagne demeure vide. Relis avertissements_structure et corrige. ` +
        (mode === "surprise"
          ? "Mode surprise : conçois tout en secret et ne révèle que l'accroche."
          : "Mode guidé : propose-moi la trame étape par étape.");
      // Message envoyé plus tard, au « Commencer l'aventure », pour lancer la
      // partie dans une nouvelle conversation liée à la campagne. L'ouverture doit
      // expliquer POURQUOI le PJ est là et lui donner une RAISON PERSONNELLE
      // d'avancer (objectif concret tiré d'un crochet lie_a_pj) — pas un décor seul.
      const message =
        mode === "surprise"
          ? "Ouvre la campagne : raconte l'accroche en expliquant pourquoi le " +
            "personnage est là et donne-lui une raison personnelle et concrète " +
            "d'avancer dans la quête (un objectif immédiat, ce qu'il risque ou " +
            "gagne, lié à son crochet personnel). Puis lance la partie."
          : "Ouvre la campagne : explique pourquoi le personnage est là et " +
            "donne-lui une raison personnelle et concrète d'avancer dans la quête " +
            "(objectif immédiat lié à son crochet), puis lance la partie.";
      // L'écran de création lit ce payload (sessionStorage) puis pilote la
      // génération lui-même — on n'affiche pas le chat pendant la création.
      try {
        sessionStorage.setItem(
          "mj-creation-en-cours",
          JSON.stringify({
            campagneId: j.id,
            consigne,
            message,
            titre: titre.trim(),
            mode,
          }),
        );
      } catch {
        /* stockage indisponible : on retombe sur le chat classique */
        window.location.href = `/chat?campagne=${encodeURIComponent(
          j.id,
        )}&message=${encodeURIComponent(consigne)}`;
        return;
      }
      window.location.href = "/campagne/creation";
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur à l'ouverture.");
    } finally {
      setEnCours(false);
    }
  }, [enCours, mode, titre, age, duree, pjSel, personnages, piliers, ton, theme]);

  // Entrée dans un champ texte = même effet que le bouton principal : « Suivant »
  // sur toutes les étapes, sauf la dernière (« theme ») où elle déclenche
  // « Ouvrir la campagne ». On respecte les mêmes conditions de validation que
  // le bouton (ex. âge obligatoire).
  const peutAvancer = !(etape === "age" && !age.trim());
  const entree = () => {
    if (enCours) return;
    if (estDerniere) ouvrir();
    else if (peutAvancer) suivant();
  };

  const titreEtape: Record<Etape, string> = {
    mode: "Quel mode de création ?",
    age: "Quel est l'âge du joueur ?",
    duree: "Quelle durée visée pour la partie ?",
    groupe: "Quels personnages portent le scénario ?",
    piliers: "Quels piliers privilégier ?",
    ton: "Quel ton souhaites-tu ?",
    theme: "Titre et idée de départ ?",
  };

  return (
    <div className="p-4 space-y-3">
      <div className="text-xs text-parchemin/50">
        Nouvelle campagne · étape {idx + 1}/{etapes.length}
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
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                entree();
              }
            }}
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
          {personnages.length === 0 ? (
            <p className="text-xs text-parchemin/50">
              Aucun personnage créé. Va d'abord en créer un dans « Personnages »,
              ou passe cette étape pour un cadrage sans PJ.
            </p>
          ) : (
            <>
              <p className="text-xs text-parchemin/50">
                Sélectionne le ou les PJ qui porteront le scénario. Le MJ adaptera
                les crochets, l'équilibrage et les épreuves à ce groupe.
              </p>
              <div className="flex flex-col gap-1.5">
                {personnages.map((p) => {
                  const actif = pjSel.includes(p.nom);
                  return (
                    <CheckboxLigne
                      key={p.nom}
                      checked={actif}
                      onToggle={() => basculerPj(p.nom)}
                    >
                      <span className="font-semibold">{p.nom}</span>
                      <span className="text-xs text-parchemin/50">
                        {p.espece} · {p.classe} niv.{p.niveau}
                      </span>
                    </CheckboxLigne>
                  );
                })}
              </div>
            </>
          )}
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
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              entree();
            }
          }}
          placeholder="ex. sombre, épique, humoristique… (option)"
          className="w-full bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
        />
      )}

      {etape === "theme" && (
        <div className="space-y-2">
          <input
            value={titre}
            onChange={(e) => setTitre(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                entree();
              }
            }}
            placeholder="Titre du scénario (option)"
            className="w-full bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
          />
          <textarea
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            onKeyDown={(e) => {
              // Entrée simple = retour à la ligne ; Ctrl+Entrée = ouvrir la campagne.
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                entree();
              }
            }}
            rows={3}
            placeholder="Une idée de départ, un lieu, une menace… (option · Ctrl+Entrée pour ouvrir)"
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
        {!estDerniere ? (
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
