"use client";

// Écran de création d'une campagne. Lance la génération du scénario (le même
// appel SSE que le chat) mais SANS afficher la conversation : on montre à la
// place ce que le moteur est en train de faire, étape par étape, déduit des
// appels d'outils du MJ. À la fin, on propose de commencer l'aventure ou de
// revenir à l'accueil.

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePerso } from "./PersoContext";

type Etape = { nom: string; phrase: string; etat: "cours" | "fait" };

// Traduction lisible des appels d'outils du MJ en étapes de création. Un outil
// inconnu retombe sur son nom brut, préfixé d'un engrenage.
const PHRASES: Record<string, string> = {
  etat_de_la_campagne: "Relis le cadrage de la campagne…",
  lister_les_campagnes: "Parcourt les campagnes existantes…",
  charger_le_personnage: "Consulte la fiche des personnages…",
  lister_les_personnages: "Recense les personnages du joueur…",
  tirer_sur_une_table: "Tire des idées d'inspiration…",
  advisory_de_difficulte: "Équilibre la difficulté des rencontres…",
  ecrire_le_scenario: "Rédige et structure le scénario…",
  faire_avancer_la_campagne: "Mets la campagne en place…",
  ouvrir_un_combat: "Prépare une rencontre…",
};

const phrase = (nom: string) => PHRASES[nom] ?? `⚙ ${nom}…`;

export default function CreationProgress({
  campagneId,
  consigne,
  message,
  titre,
  mode,
}: {
  campagneId: string;
  consigne: string;
  message: string;
  titre: string;
  mode: string;
}) {
  const { nom } = usePerso();
  const [etapes, setEtapes] = useState<Etape[]>([]);
  const [enCours, setEnCours] = useState(true);
  const [resultat, setResultat] = useState("");
  const [erreur, setErreur] = useState("");
  const lanceRef = useRef(false);

  const lancer = useCallback(async () => {
    setEnCours(true);
    let courant = "";
    const ctrl = new AbortController();
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          message: consigne,
          chat_id: `creation-${campagneId}`,
          historique: [],
          personnage: nom,
          campagne_id: campagneId,
        }),
      });
      const lecteur = r.body!.getReader();
      const decodeur = new TextDecoder();
      let tampon = "";
      for (;;) {
        const { value, done } = await lecteur.read();
        if (done) break;
        tampon += decodeur.decode(value, { stream: true });
        const blocs = tampon.split("\n\n");
        tampon = blocs.pop() ?? "";
        for (const bloc of blocs) {
          let evt = "message";
          let data = "";
          for (const ligne of bloc.split("\n")) {
            if (ligne.startsWith("event: ")) evt = ligne.slice(7).trim();
            else if (ligne.startsWith("data: ")) data += ligne.slice(6);
          }
          if (!data) continue;
          const payload = JSON.parse(data);
          if (evt === "outil") {
            const nomOutil: string = payload.nom;
            if (payload.etat === "appel") {
              setEtapes((prev) =>
                prev.some((e) => e.nom === nomOutil)
                  ? prev.map((e) =>
                      e.nom === nomOutil ? { ...e, etat: "cours" } : e,
                    )
                  : [...prev, { nom: nomOutil, phrase: phrase(nomOutil), etat: "cours" }],
              );
            } else {
              setEtapes((prev) =>
                prev.map((e) =>
                  e.nom === nomOutil ? { ...e, etat: "fait" } : e,
                ),
              );
            }
          } else if (evt === "fin") {
            courant = payload.texte ?? courant;
          } else if (evt === "erreur") {
            setErreur(payload.message ?? "Erreur pendant la création.");
          }
        }
      }
      setResultat(courant);
    } catch (e) {
      if ((e as Error).name !== "AbortError")
        setErreur("Connexion au serveur perdue.");
    } finally {
      setEnCours(false);
    }
  }, [consigne, campagneId, nom]);

  useEffect(() => {
    if (lanceRef.current) return;
    lanceRef.current = true;
    lancer();
  }, [lancer]);

  // Lien « commencer » : nouvelle conversation liée à la campagne, qui lance la
  // partie (le scénario est déjà persisté par le MJ pendant la création).
  const urlChat =
    `/chat?campagne=${encodeURIComponent(campagneId)}` +
    `&message=${encodeURIComponent(message)}&nouveau=1`;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold text-or">
            {titre ? titre : "Ta campagne"}
          </h1>
          <p className="text-sm text-parchemin/60">
            {enCours
              ? "Le Maître du Jeu conçoit ton aventure…"
              : "L'aventure est prête."}
          </p>
        </div>

        {/* Étapes réalisées, déduites des appels d'outils du MJ. */}
        <ol className="space-y-2">
          {etapes.length === 0 && enCours && (
            <li className="text-parchemin/40 italic text-sm">
              Le MJ se met en place…
            </li>
          )}
          {etapes.map((e) => (
            <li
              key={e.nom}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${
                e.etat === "fait"
                  ? "bg-white/5 text-parchemin/70"
                  : "bg-or/10 text-or"
              }`}
            >
              <span className="w-5 text-center">
                {e.etat === "fait" ? "✓" : <span className="animate-pulse">⚙</span>}
              </span>
              {e.phrase}
            </li>
          ))}
        </ol>

        {erreur && (
          <div className="rounded-lg border border-sang/40 bg-sang/10 p-3 text-sm text-parchemin/80">
            ⚠ {erreur}
          </div>
        )}

        {/* Fin de création : on propose de commencer ou de revenir à l'accueil. */}
        {!enCours && !erreur && (
          <div className="space-y-4 pt-2">
            <div className="rounded-lg border border-or/30 bg-black/20 p-4">
              <p className="text-xs uppercase tracking-wide text-or/70 mb-2">
                {mode === "surprise" ? "L'accroche" : "La trame"}
              </p>
              <p className="text-sm text-parchemin/80 whitespace-pre-wrap">
                {resultat ||
                  "Le scénario est en place. Ouvre la campagne pour la découvrir."}
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href={urlChat}
                className="rounded-lg bg-emerald-700/70 hover:bg-emerald-700 text-white font-semibold px-5 py-2.5 text-sm"
              >
                ▶ Commencer l'aventure
              </Link>
              <Link
                href="/"
                className="rounded-lg bg-white/10 hover:bg-white/20 px-5 py-2.5 text-sm"
              >
                Retour à l'accueil
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
