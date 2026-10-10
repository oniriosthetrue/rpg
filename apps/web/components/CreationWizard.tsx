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
  progression?: string;
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

  const finaliser = useCallback(async () => {
    if (enCours) return;
    setEnCours(true);
    setErreur("");
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
          pour bâtir ton personnage. Tu peux répondre, taper « au hasard », ou
          « continue ».
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
        <div className="flex flex-wrap gap-1.5">
          {q.options.slice(0, 40).map((o) => (
            <button
              key={o}
              onClick={() => repondre(o)}
              disabled={enCours}
              className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 text-xs disabled:opacity-40"
            >
              {o}
            </button>
          ))}
        </div>
      )}

      {erreur && <div className="text-red-400 text-sm">{erreur}</div>}

      <div className="flex gap-2">
        <input
          value={saisie}
          onChange={(e) => setSaisie(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && saisie.trim()) repondre(saisie.trim());
          }}
          placeholder="Ta réponse (ou « au hasard »)…"
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

      <div className="flex gap-2 text-xs">
        <button
          onClick={() => repondre("au hasard")}
          disabled={enCours}
          className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 disabled:opacity-40"
        >
          🎲 Au hasard
        </button>
        <button
          onClick={finaliser}
          disabled={enCours}
          className="rounded bg-emerald-700/60 hover:bg-emerald-700 px-2 py-1 disabled:opacity-40"
        >
          Finaliser
        </button>
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
