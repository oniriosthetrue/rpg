"use client";

// Chat du MJ : multi-conversations (localStorage), stop (client + serveur),
// citations RAG. Consomme le SSE du backend (token / outil / citations / fin / erreur).

import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "./Markdown";
import { usePerso } from "./PersoContext";

type Source = { nom: string; source: string; edition?: string };
type Message = { role: "user" | "assistant"; content: string; citations?: Source[] };
type Conversation = {
  id: string;
  titre: string;
  messages: Message[];
  personnage: string;
  date: number;
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
  const fondRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const actif = conversations.find((c) => c.id === actifId);

  // Chargement initial : restaure ou crée la première conversation.
  useEffect(() => {
    const toutes = chargerToutes();
    if (toutes.length) {
      setConversations(toutes);
      setActifId(toutes[0].id);
    } else {
      const c = nouveauChat(nom);
      setConversations([c]);
      setActifId(c.id);
    }
    // Liaison depuis l'écran Campagne : /chat?campagne=<id>&message=<texte>.
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search);
      const camp = p.get("campagne");
      if (camp) setCampagneId(camp);
      const msg = p.get("message");
      if (msg) setSaisie(msg);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persistance à chaque changement.
  useEffect(() => {
    if (conversations.length && typeof localStorage !== "undefined")
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
    const c = nouveauChat(nom);
    setConversations((prev) => [c, ...prev]);
    setActifId(c.id);
  }, [nom]);

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

  const envoyer = useCallback(async () => {
    const texte = saisie.trim();
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
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => {
                setActifId(c.id);
                // Restaure le PJ de cette conversation (évite qu'une vieille
                // conversation parle du PJ actif global changé entre-temps).
                if (c.personnage) setNom(c.personnage);
              }}
              className={`group cursor-pointer rounded-lg px-2 py-1.5 text-xs ${
                c.id === actifId ? "bg-or/20 text-or" : "hover:bg-white/5"
              }`}
            >
              <div className="truncate">{c.titre}</div>
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
          ))}
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
          {messages.length === 0 && (
            <p className="text-parchemin/40 italic">
              Décris la scène ou pose ta question au MJ…
            </p>
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
              onClick={envoyer}
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
