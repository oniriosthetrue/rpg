"use client";

// Chat du MJ : multi-conversations (localStorage), stop (client + serveur),
// citations RAG. Consomme le SSE du backend (token / outil / citations / fin / erreur).

import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "./Markdown";
import { usePerso } from "./PersoContext";
import { jdr } from "@/lib/jdr";

type Source = { nom: string; source: string; edition?: string };
type Message = { role: "user" | "assistant"; content: string; citations?: Source[] };
type Conversation = {
  id: string;
  titre: string;
  messages: Message[];
  personnage: string;
  date: number;
  // Campagne ciblée par cette conversation (liée depuis l'écran Campagne /
  // création). Permet de conserver le lien au rechargement et d'afficher le
  // titre de la campagne plutôt que la consigne brute.
  campagneId?: string;
};

const CLE = "mj-conversations";

function chargerToutes(): Conversation[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const brut = localStorage.getItem(CLE);
    return brut ? (JSON.parse(brut) as Conversation[]) : [];
  } catch {
    return [];
  }
}

function nouveauChat(personnage: string): Conversation {
  return {
    id: typeof crypto !== "undefined" ? crypto.randomUUID() : `c-${Date.now()}`,
    titre: "Nouvelle conversation",
    messages: [],
    personnage,
    date: Date.now(),
  };
}

export default function Chat() {
  const { personnages, nom, setNom, onChangementFiche } = usePerso();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [actifId, setActifId] = useState("");
  const [saisie, setSaisie] = useState("");
  const [enCours, setEnCours] = useState(false);
  const [outil, setOutil] = useState("");
  const [campagneId, setCampagneId] = useState("");
  // Titres et identifiants des campagnes existantes : sert à titrer les
  // conversations liées et à masquer celles d'une campagne supprimée.
  const [titresCampagnes, setTitresCampagnes] = useState<Record<string, string>>(
    {},
  );
  const [idsCampagnes, setIdsCampagnes] = useState<Set<string>>(new Set());
  // True une fois la liste des campagnes reçue : la purge des conversations
  // orphelines ne s'exécute qu'après (sinon on tout effacerait avant de savoir).
  const [campagnesChargees, setCampagnesChargees] = useState(false);
  const fondRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Message d'amorce passé par l'écran Campagne (/chat?…&message=…) : auto-envoyé
  // une fois la conversation active prête (sinon il resterait en saisie sans effet).
  const amorceRef = useRef<string>("");

  const actif = conversations.find((c) => c.id === actifId);

  // Chargement initial : restaure ou crée la première conversation.
  useEffect(() => {
    let toutes = chargerToutes();
    let idActif = toutes[0]?.id ?? "";
    if (!toutes.length) {
      const c = nouveauChat(nom);
      toutes = [c];
      idActif = c.id;
    }
    // Liaison depuis l'écran Campagne / création :
    // /chat?campagne=<id>&message=<texte>[&nouveau=1].
    let campagneLue = "";
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search);
      campagneLue = p.get("campagne") ?? "";
      const msg = p.get("message");
      if (msg) amorceRef.current = msg;
      // `nouveau=1` (retour de l'écran de création) : on repart d'une
      // conversation vierge liée à la campagne, sans reprendre les anciennes.
      if (p.get("nouveau") === "1") {
        const c = nouveauChat(nom);
        toutes = [c, ...toutes];
        idActif = c.id;
      }
      // Une fois l'amorce lue, on retire `message` et `nouveau` de l'URL : sinon
      // tout rechargement (ou suppression de toutes les conversations suivie d'un
      // rafraîchissement) relirait le message et relancerait l'auto-envoi — le
      // texte « supprimé » réapparaîtrait.
      if (p.has("message") || p.has("nouveau")) {
        p.delete("message");
        p.delete("nouveau");
        const q = p.toString();
        const url =
          window.location.pathname + (q ? `?${q}` : "") + window.location.hash;
        window.history.replaceState({}, "", url);
      }
    }
    // La conversation active porte la campagne ciblée : le lien est ainsi
    // conservé au rechargement et au changement de conversation.
    if (campagneLue) {
      setCampagneId(campagneLue);
      toutes = toutes.map((c) =>
        c.id === idActif ? { ...c, campagneId: campagneLue } : c,
      );
    }
    setConversations(toutes);
    setActifId(idActif);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Récupère les campagnes existantes (titres + ids) pour l'affichage de la liste.
  useEffect(() => {
    jdr.get<{ campagnes: { id: string; titre: string }[] }>("/campagne")
      .then((j) => {
        const t: Record<string, string> = {};
        const ids = new Set<string>();
        for (const c of j.campagnes) {
          t[c.id] = c.titre || c.id;
          ids.add(c.id);
        }
        setTitresCampagnes(t);
        setIdsCampagnes(ids);
        setCampagnesChargees(true);
      })
      .catch(() => {
        /* liste indisponible : on garde les titres internes */
        setCampagnesChargees(true);
      });
  }, []);

  // Règle : une conversation affichée doit être reliée à une campagne existante.
  // On purge les orphelines (campagne supprimée) et les libres (sans campagne),
  // puis on répare la conversation active (bascule sur une valide, ou recrée une
  // conversation liée à la campagne ciblée si plus rien n'est jouable).
  useEffect(() => {
    if (!campagnesChargees) return;
    const valides = conversations.filter(
      (c) => c.campagneId && idsCampagnes.has(c.campagneId),
    );
    if (valides.length !== conversations.length) {
      setConversations(valides);
      return; // l'effet rerunera et réparera l'actif sur la liste propre
    }
    const courant = valides.find((c) => c.id === actifId);
    if (!courant) {
      if (valides.length) {
        setActifId(valides[0].id);
        setCampagneId(valides[0].campagneId ?? "");
      } else if (campagneId && idsCampagnes.has(campagneId)) {
        const c = nouveauChat(nom);
        c.campagneId = campagneId;
        setConversations([c]);
        setActifId(c.id);
      }
    }
  }, [conversations, actifId, campagnesChargees, idsCampagnes, campagneId, nom]);

  // Persistance à chaque changement (même vide : la purge doit être mémorisée).
  useEffect(() => {
    if (typeof localStorage !== "undefined")
      localStorage.setItem(CLE, JSON.stringify(conversations));
  }, [conversations]);

  const majConversation = useCallback(
    (id: string, patch: Partial<Conversation>) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === id ? { ...c, ...patch, date: Date.now() } : c,
        ),
      );
    },
    [],
  );

  const nouveau = useCallback(() => {
    // Une nouvelle conversation se rattache à la campagne active ; sans quête
    // ciblée, on ne peut pas créer de conversation (règle : tout est lié à une
    // campagne existante) — on renvoie vers l'écran Campagne.
    if (!campagneId || !idsCampagnes.has(campagneId)) {
      window.location.href = "/campagne";
      return;
    }
    const c = nouveauChat(nom);
    c.campagneId = campagneId;
    setConversations((prev) => [c, ...prev]);
    setActifId(c.id);
  }, [nom, campagneId, idsCampagnes]);

  const supprimer = useCallback(
    (id: string) => {
      setConversations((prev) => {
        const reste = prev.filter((c) => c.id !== id);
        if (id === actifId) {
          if (reste.length) setActifId(reste[0].id);
          else {
            const c = nouveauChat(nom);
            setActifId(c.id);
            return [c];
          }
        }
        return reste;
      });
    },
    [actifId, nom],
  );

  const renommer = useCallback(
    (id: string) => {
      const c = conversations.find((x) => x.id === id);
      const t = window.prompt("Titre de la conversation", c?.titre ?? "");
      if (t != null) majConversation(id, { titre: t });
    },
    [conversations, majConversation],
  );

  const envoyer = useCallback(async (texteSuppleant?: string) => {
    const texte = (texteSuppleant ?? saisie).trim();
    if (!texte || enCours || !actif) return;

    const historique = actif.messages;
    const titre = actif.messages.length === 0 ? texte.slice(0, 40) : actif.titre;
    const messagesApres: Message[] = [
      ...historique,
      { role: "user", content: texte },
      { role: "assistant", content: "" },
    ];
    majConversation(actif.id, { messages: messagesApres, titre });
    setSaisie("");
    setEnCours(true);
    setOutil("");

    let courant = "";
    let citations: Source[] = [];
    const majDernier = () => {
      const copie = messagesApres.slice();
      copie[copie.length - 1] = { role: "assistant", content: courant, citations };
      majConversation(actif.id, { messages: copie });
      requestAnimationFrame(() =>
        fondRef.current?.scrollTo({ top: fondRef.current.scrollHeight }),
      );
    };

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          message: texte,
          chat_id: actif.id,
          historique,
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
          if (evt === "token") {
            courant += payload.texte;
            majDernier();
          } else if (evt === "citations") {
            citations = payload.sources ?? [];
            majDernier();
          } else if (evt === "outil") {
            setOutil(payload.etat === "appel" ? `⚙ ${payload.nom}…` : "");
          } else if (evt === "fin") {
            courant = payload.texte ?? courant;
            majDernier();
            onChangementFiche();
          } else if (evt === "erreur") {
            courant = `⚠ ${payload.message}`;
            majDernier();
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        courant = courant || "⚠ Erreur de connexion au serveur.";
        majDernier();
      }
    } finally {
      setEnCours(false);
      setOutil("");
      abortRef.current = null;
    }
  }, [saisie, enCours, actif, nom, campagneId, majConversation, onChangementFiche]);

  // Auto-envoi de l'amorce venue de l'écran Campagne, une seule fois, dès que la
  // conversation active est prête (le message ne doit pas rester en saisie).
  useEffect(() => {
    if (!amorceRef.current || !actif || enCours) return;
    const msg = amorceRef.current;
    amorceRef.current = "";
    envoyer(msg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actifId, enCours]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const messages = actif?.messages ?? [];

  return (
    <div className="flex h-full">
      {/* Liste des conversations */}
      <div className="hidden sm:flex w-44 shrink-0 flex-col border-r border-white/10 bg-black/10">
        <button
          onClick={nouveau}
          className="m-2 rounded-lg bg-or/80 hover:bg-or text-encre font-semibold px-3 py-2 text-sm"
        >
          + Nouveau
        </button>
        <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
          {conversations.map((c) => {
            // Une conversation liée à une campagne supprimée disparaît de la liste.
            if (c.campagneId && !idsCampagnes.has(c.campagneId)) return null;
            const titre =
              c.campagneId && titresCampagnes[c.campagneId]
                ? `📜 ${titresCampagnes[c.campagneId]}`
                : c.titre;
            return (
            <div
              key={c.id}
              onClick={() => {
                setActifId(c.id);
                // Bascule la campagne ciblée sur celle de la conversation.
                setCampagneId(c.campagneId ?? "");
                // Restaure le PJ de cette conversation (évite qu'une vieille
                // conversation parle du PJ actif global changé entre-temps).
                if (c.personnage) setNom(c.personnage);
              }}
              className={`group cursor-pointer rounded-lg px-2 py-1.5 text-xs ${
                c.id === actifId ? "bg-or/20 text-or" : "hover:bg-white/5"
              }`}
            >
              <div className="truncate">{titre}</div>
              <div className="flex gap-2 opacity-0 group-hover:opacity-100 text-parchemin/50">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    renommer(c.id);
                  }}
                  title="Renommer"
                >
                  ✎
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    supprimer(c.id);
                  }}
                  title="Supprimer"
                >
                  🗑
                </button>
              </div>
            </div>
            );
          })}
        </div>
      </div>

      {/* Fil de discussion */}
      <div className="flex flex-col flex-1 min-w-0">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10">
          <select
            value={nom}
            onChange={(e) => {
              setNom(e.target.value);
              // Le PJ choisi devient celui de la conversation active.
              if (actif) majConversation(actif.id, { personnage: e.target.value });
            }}
            className="bg-white/5 rounded px-2 py-1 text-sm outline-none"
          >
            {personnages.length === 0 && (
              <option value="">(aucun personnage)</option>
            )}
            {personnages.map((p) => (
              <option key={p.nom} value={p.nom}>
                {p.nom} — {p.classe} niv.{p.niveau}
              </option>
            ))}
          </select>
          <button
            onClick={nouveau}
            className="sm:hidden text-xs text-or"
            title="Nouveau chat"
          >
            + Nouveau
          </button>
        </div>

        <div ref={fondRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {!actif ? (
            <p className="text-parchemin/40 italic">
              Aucune quête active. Ouvre une campagne pour commencer l'aventure.
            </p>
          ) : (
            messages.length === 0 && (
              <p className="text-parchemin/40 italic">
                Décris la scène ou pose ta question au MJ…
              </p>
            )
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              {m.role === "user" ? (
                <span className="inline-block bg-or/20 rounded-lg px-3 py-2 max-w-[80%] text-left whitespace-pre-wrap">
                  {m.content}
                </span>
              ) : (
                <div className="max-w-[90%]">
                  {m.content ? (
                    <>
                      <Markdown source={m.content} />
                      {m.citations && m.citations.length > 0 && (
                        <details className="mt-1 text-xs text-parchemin/50">
                          <summary className="cursor-pointer hover:text-or">
                            📚 {m.citations.length} source(s) SRD
                          </summary>
                          <ul className="mt-1 pl-4 list-disc">
                            {m.citations.map((s, j) => (
                              <li key={j}>
                                {s.nom} — <em>{s.source}</em>
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </>
                  ) : enCours ? (
                    <span className="text-parchemin/40">…</span>
                  ) : null}
                </div>
              )}
            </div>
          ))}
          {outil && (
            <div className="text-xs text-or/70 animate-pulse">{outil}</div>
          )}
        </div>

        <div className="border-t border-white/10 p-3 flex gap-2">
          <textarea
            value={saisie}
            onChange={(e) => setSaisie(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                envoyer();
              }
            }}
            rows={2}
            placeholder="Que fais-tu ?"
            className="flex-1 bg-white/5 rounded-lg px-3 py-2 resize-none outline-none focus:ring-1 focus:ring-or/50"
          />
          {enCours ? (
            <button
              onClick={stop}
              className="bg-sang/80 hover:bg-sang text-parchemin font-semibold rounded-lg px-4"
            >
              ⏹ Stop
            </button>
          ) : (
            <button
              onClick={() => envoyer()}
              className="bg-or/80 hover:bg-or text-encre font-semibold rounded-lg px-4"
            >
              Envoyer
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
