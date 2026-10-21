"use client";

// Assistant de création guidée. Pilote l'API /api/creation (chat_id préfixé
// « creation- » pour ne pas entrer en collision avec l'identifiant de chat).

import { useCallback, useState } from "react";
import { jdr, ErreurJdr } from "@/lib/jdr";

type Reponse = {
  ok: boolean;
  type: string; // question | fiche | abandon | erreur
  etape?: string;
  question?: string;
  options?: string[];
  limites?: Record<string, number> | null;
  progression?: string | null;
  avertissements?: string[];
  message?: string;
  erreur?: string;
  personnage?: { nom: string };
};

export default function CreationWizard({
  onTermine,
}: {
  onTermine: () => void;
}) {
  const [chatId] = useState(
    () => `creation-${Date.now()}-${Math.floor(Math.random() * 1e6)}`,
  );
  const [etat, setEtat] = useState<"debut" | "enCours" | "fini" | "abandon">("debut");
  const [q, setQ] = useState<Reponse | null>(null);
  const [saisie, setSaisie] = useState("");
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState("");
  // Double confirmation pour « Finaliser » : cette action complète TOUTES les
  // étapes restantes au hasard et clôture la fiche. On évite le clic accidentel.
  const [confirmerFinal, setConfirmerFinal] = useState(false);
  // Sélection en cours pour les étapes à choix multiples (compétences, sorts) :
  // le moteur attend TOUTES les options en une seule réponse (sinon il n'en
  // voit qu'une, tire le reste au hasard et passe à l'étape suivante).
  const [selection, setSelection] = useState<string[]>([]);
  const multi = !!q && (q.etape === "competences" || q.etape === "sorts");
  // Étape en saisie libre (aucune option proposée) : ex. le « nom ». On affiche
  // alors un champ texte + OK, en plus du bouton « Au hasard ».
  const libre = !!q && (!q.options || q.options.length === 0);

  // Groupe d'une option pour les limites : « total » pour les compétences,
  // « mineur » / « 1er niveau » pour les sorts (selon le préfixe de l'option).
  const groupeDe = (o: string): string => {
    if (q?.etape === "sorts") {
      if (o.startsWith("[mineur]")) return "mineur";
      if (o.startsWith("[1er niveau]")) return "1er niveau";
    }
    return "total";
  };
  const limiteDe = (groupe: string): number | undefined => q?.limites?.[groupe];
  const compteGroupe = (groupe: string): number =>
    selection.filter((o) => groupeDe(o) === groupe).length;
  // Peut-on ajouter cette option sans dépasser la limite de son groupe ?
  const peutAjouter = (o: string): boolean => {
    const lim = limiteDe(groupeDe(o));
    return lim === undefined || compteGroupe(groupeDe(o)) < lim;
  };

  const demarrer = useCallback(async () => {
    setEnCours(true);
    setErreur("");
    try {
      const r = await jdr.post<Reponse>("/creation", { chat_id: chatId });
      setQ(r);
      setEtat("enCours");
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur au démarrage.");
    } finally {
      setEnCours(false);
    }
  }, [chatId]);

  const repondre = useCallback(
    async (reponse: string) => {
      if (enCours) return;
      setEnCours(true);
      setErreur("");
      try {
        const r = await jdr.post<Reponse>(
          `/creation/${encodeURIComponent(chatId)}/reponse`,
          { reponse },
        );
        setQ(r);
        setSaisie("");
        setSelection([]);
        setConfirmerFinal(false);
        if (r.type === "fiche") setEtat("fini");
        else if (r.type === "abandon") setEtat("abandon");
      } catch (e) {
        setErreur(e instanceof ErreurJdr ? e.message : "Erreur de réponse.");
      } finally {
        setEnCours(false);
      }
    },
    [chatId, enCours],
  );

  const revenir = useCallback(async () => {
    if (enCours) return;
    setEnCours(true);
    setErreur("");
    try {
      const r = await jdr.post<Reponse>(
        `/creation/${encodeURIComponent(chatId)}/retour`,
      );
      setQ(r);
      setSaisie("");
      setSelection([]);
      setConfirmerFinal(false);
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur de retour.");
    } finally {
      setEnCours(false);
    }
  }, [chatId, enCours]);

  const finaliser = useCallback(async () => {
    if (enCours) return;
    setEnCours(true);
    setErreur("");
    setConfirmerFinal(false);
    try {
      const r = await jdr.post<Reponse>(
        `/creation/${encodeURIComponent(chatId)}/finaliser`,
      );
      setQ(r);
      setEtat("fini");
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur de finalisation.");
    } finally {
      setEnCours(false);
    }
  }, [chatId, enCours]);

  const abandonner = useCallback(async () => {
    try {
      await jdr.post(`/creation/${encodeURIComponent(chatId)}/abandon`);
    } catch {
      /* ignore */
    }
    setEtat("abandon");
  }, [chatId]);

  if (etat === "debut")
    return (
      <div className="p-4 space-y-3">
        <p className="text-parchemin/70">
          Le MJ te pose une série de questions (classe, espèce, caractéristiques…)
          pour bâtir ton personnage. Choisis une option, ou tape « 🎲 Au hasard ».
        </p>
        {erreur && <div className="text-red-400 text-sm">{erreur}</div>}
        <button
          onClick={demarrer}
          disabled={enCours}
          className="rounded-lg bg-or/80 hover:bg-or text-encre font-semibold px-4 py-2 disabled:opacity-40"
        >
          {enCours ? "…" : "Commencer la création"}
        </button>
      </div>
    );

  if (etat === "abandon")
    return (
      <div className="p-4 space-y-3">
        <p className="text-parchemin/70">Création abandonnée.</p>
        <button
          onClick={demarrer}
          className="rounded-lg bg-or/80 hover:bg-or text-encre font-semibold px-4 py-2"
        >
          Recommencer
        </button>
      </div>
    );

  if (etat === "fini")
    return (
      <div className="p-4 space-y-3">
        <p className="text-emerald-400">
          ✓ Personnage créé{q?.personnage?.nom ? ` : ${q.personnage.nom}` : ""}.
        </p>
        <button
          onClick={onTermine}
          className="rounded-lg bg-or/80 hover:bg-or text-encre font-semibold px-4 py-2"
        >
          Voir mes personnages
        </button>
      </div>
    );

  return (
    <div className="p-4 space-y-3">
      <div className="text-xs text-parchemin/50">
        Étape {q?.etape} {q?.progression ? `· ${q.progression}` : ""}
      </div>
      <p className="font-semibold text-or">{q?.question}</p>

      {q?.avertissements && q.avertissements.length > 0 && (
        <ul className="text-xs text-sang/80 list-disc pl-5">
          {q.avertissements.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      )}

      {q?.options && q.options.length > 0 && (
        <div className={multi ? "flex flex-wrap gap-1.5" : "flex flex-col gap-1.5"}>
          {q.options.slice(0, 40).map((o) => {
            const active = selection.includes(o);
            const bloque = multi && !active && !peutAjouter(o);
            return (
              <button
                key={o}
                onClick={() =>
                  multi
                    ? setSelection((s) =>
                        s.includes(o) ? s.filter((x) => x !== o) : peutAjouter(o) ? [...s, o] : s,
                      )
                    : repondre(o)
                }
                disabled={enCours || bloque}
                title={bloque ? "Limite atteinte pour ce groupe" : undefined}
                className={`rounded px-2 py-1 text-left text-xs disabled:opacity-40 ${
                  multi ? "" : "w-full"
                } ${
                  active
                    ? "bg-or text-encre font-semibold"
                    : "bg-white/10 hover:bg-white/20"
                }`}
              >
                {o}
              </button>
            );
          })}
        </div>
      )}

      {multi && (
        <div className="flex flex-col gap-1 text-xs">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {q?.etape === "sorts" ? (
              <>
                <span className="text-parchemin/70">
                  Sorts mineurs :{" "}
                  <span className="font-semibold text-or">
                    {compteGroupe("mineur")}/{limiteDe("mineur") ?? "?"}
                  </span>
                </span>
                <span className="text-parchemin/70">
                  1er niveau :{" "}
                  <span className="font-semibold text-or">
                    {compteGroupe("1er niveau")}/{limiteDe("1er niveau") ?? "?"}
                  </span>
                </span>
              </>
            ) : (
              <span className="text-parchemin/70">
                Compétences :{" "}
                <span className="font-semibold text-or">
                  {selection.length}/{limiteDe("total") ?? "?"}
                </span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => selection.length && repondre(selection.join(", "))}
              disabled={enCours || selection.length === 0}
              className="rounded-lg bg-or/80 hover:bg-or text-encre font-semibold px-3 py-1 disabled:opacity-40"
            >
              Valider ({selection.length})
            </button>
            <span className="text-parchemin/50">
              Sélectionne {q?.etape === "sorts" ? "tes sorts" : "tes compétences"},
              puis Valider. Le reste sera tiré au hasard.
            </span>
          </div>
        </div>
      )}

      {libre && (
        <div className="flex gap-2">
          <input
            value={saisie}
            onChange={(e) => setSaisie(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && saisie.trim()) repondre(saisie.trim());
            }}
            placeholder="Ta réponse…"
            className="flex-1 bg-white/5 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-or/50"
          />
          <button
            onClick={() => saisie.trim() && repondre(saisie.trim())}
            disabled={enCours}
            className="rounded-lg bg-or/80 hover:bg-or text-encre font-semibold px-3 disabled:opacity-40"
          >
            OK
          </button>
        </div>
      )}

      {erreur && <div className="text-red-400 text-sm">{erreur}</div>}

      <div className="flex gap-2 text-xs">
        <button
          onClick={revenir}
          disabled={enCours}
          className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 disabled:opacity-40"
        >
          ⬅ Retour
        </button>
        <button
          onClick={() => repondre("au hasard")}
          disabled={enCours}
          className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 disabled:opacity-40"
        >
          🎲 Au hasard
        </button>
        {confirmerFinal ? (
          <button
            onClick={finaliser}
            disabled={enCours}
            className="rounded bg-emerald-600 hover:bg-emerald-500 text-encre font-semibold px-2 py-1 disabled:opacity-40"
          >
            Confirmer ? Le reste sera tiré au hasard
          </button>
        ) : (
          <button
            onClick={() => setConfirmerFinal(true)}
            disabled={enCours}
            className="rounded bg-emerald-700/60 hover:bg-emerald-700 px-2 py-1 disabled:opacity-40"
          >
            Finaliser
          </button>
        )}
        <button
          onClick={abandonner}
          disabled={enCours}
          className="rounded bg-sang/60 hover:bg-sang px-2 py-1 disabled:opacity-40"
        >
          Abandonner
        </button>
      </div>
    </div>
  );
}
