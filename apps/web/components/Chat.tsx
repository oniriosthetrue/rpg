"use client";

import { useCallback, useRef, useState } from "react";
import Markdown from "./Markdown";

type Message = { role: "user" | "assistant"; content: string };

type Props = {
  chatId: string;
  personnage: string;
  onChangementFiche: () => void;
};

// Consomme le flux SSE du backend (events : token / outil / fin / erreur).
export default function Chat({ chatId, personnage, onChangementFiche }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [saisie, setSaisie] = useState("");
  const [enCours, setEnCours] = useState(false);
  const [outil, setOutil] = useState("");
  const fondRef = useRef<HTMLDivElement>(null);

  const envoyer = useCallback(async () => {
    const texte = saisie.trim();
    if (!texte || enCours) return;

    const historique = messages;
    const nouveau: Message[] = [...messages, { role: "user", content: texte }];
    setMessages([...nouveau, { role: "assistant", content: "" }]);
    setSaisie("");
    setEnCours(true);
    setOutil("");

    let courant = "";
    const majDernier = (s: string) => {
      courant = s;
      setMessages((prev) => {
        const copie = prev.slice();
        copie[copie.length - 1] = { role: "assistant", content: s };
        return copie;
      });
      requestAnimationFrame(() =>
        fondRef.current?.scrollTo({ top: fondRef.current.scrollHeight }),
      );
    };

    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: texte,
          chat_id: chatId,
          historique,
          personnage,
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
          if (evt === "token") majDernier(courant + payload.texte);
          else if (evt === "outil")
            setOutil(
              payload.etat === "appel" ? `⚙ ${payload.nom}…` : "",
            );
          else if (evt === "fin") {
            majDernier(payload.texte ?? courant);
            onChangementFiche();
          } else if (evt === "erreur")
            majDernier(`⚠ ${payload.message}`);
        }
      }
    } catch (e) {
      majDernier(`⚠ Erreur de connexion au serveur.`);
    } finally {
      setEnCours(false);
      setOutil("");
    }
  }, [saisie, enCours, messages, chatId, personnage, onChangementFiche]);

  return (
    <div className="flex flex-col h-full">
      <div ref={fondRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-parchemin/40 italic">
            Décris la scène ou pose ta question au MJ…
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            {m.role === "user" ? (
              <span className="inline-block bg-or/20 rounded-lg px-3 py-2 max-w-[80%] text-left">
                {m.content}
              </span>
            ) : (
              <div className="max-w-[90%]">
                {m.content ? (
                  <Markdown source={m.content} />
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
        <button
          onClick={envoyer}
          disabled={enCours}
          className="bg-or/80 hover:bg-or text-encre font-semibold rounded-lg px-4 disabled:opacity-40"
        >
          {enCours ? "…" : "Envoyer"}
        </button>
      </div>
    </div>
  );
}
