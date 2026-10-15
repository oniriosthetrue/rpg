"use client";

// Formulaire générique de connexion / inscription. Envoie en POST vers
// `/api/auth/<action>` (relais Next → backend) et redirige au succès.

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

type Props = {
  action: "login" | "register";
  titre: string;
  sousTitre: string;
  libelleBouton: string;
  lien: { texte: string; href: string };
};

export default function AuthForm({ action, titre, sousTitre, libelleBouton, lien }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [mdp, setMdp] = useState("");
  const [erreur, setErreur] = useState("");
  const [info, setInfo] = useState("");
  const [lienVerif, setLienVerif] = useState("");
  const [charge, setCharge] = useState(false);

  async function soumettre(e: React.FormEvent) {
    e.preventDefault();
    setErreur("");
    setInfo("");
    setCharge(true);
    try {
      const r = await fetch(`/api/auth/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, mot_de_passe: mdp }),
      });
      const json = await r.json();
      if (json.ok === false) {
        setErreur(json.erreur ?? "Une erreur est survenue.");
        setCharge(false);
        return;
      }
      if (action === "login") {
        const retour = params.get("retour") || "/";
        router.replace(retour);
        router.refresh();
      } else {
        // Inscription : le compte est créé. On connecte directement si le
        // backend l'accepte, sinon on affiche le message de vérification.
        if (json.verifie) {
          const r2 = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, mot_de_passe: mdp }),
          });
          const j2 = await r2.json();
          if (j2.ok) {
            router.replace("/");
            router.refresh();
            return;
          }
        }
        setInfo(
          json.lien_verification
            ? "Compte créé. Confirme ton adresse en ouvrant le lien ci-dessous (mode console, SMTP non configuré)."
            : "Compte créé ! Vérifie ta boîte mail pour confirmer ton adresse.",
        );
        if (json.lien_verification) setLienVerif(json.lien_verification);
        setCharge(false);
      }
    } catch {
      setErreur("Le serveur est injoignable.");
      setCharge(false);
    }
  }

  return (
    <div className="w-full max-w-sm mx-auto p-6">
      <div className="text-center mb-6">
        <h1 className="text-2xl font-bold text-or">{titre}</h1>
        <p className="text-parchemin/60 text-sm mt-1">{sousTitre}</p>
      </div>

      <form onSubmit={soumettre} className="space-y-4">
        <div>
          <label className="block text-xs text-parchemin/60 mb-1" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm focus:border-or/60 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-xs text-parchemin/60 mb-1" htmlFor="mdp">
            Mot de passe
          </label>
          <input
            id="mdp"
            type="password"
            required
            minLength={8}
            autoComplete={action === "login" ? "current-password" : "new-password"}
            value={mdp}
            onChange={(e) => setMdp(e.target.value)}
            className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm focus:border-or/60 focus:outline-none"
          />
        </div>

        {erreur && <div className="text-red-400 text-xs">{erreur}</div>}
        {info && (
          <div className="text-emerald-400 text-xs break-all">
            {info}
            {lienVerif && (
              <>
                {" "}
                <a className="underline" href={lienVerif}>
                  Ouvrir le lien de vérification
                </a>
              </>
            )}
          </div>
        )}

        <button
          type="submit"
          disabled={charge}
          className="w-full rounded-lg bg-or/80 hover:bg-or text-encre font-semibold py-2 disabled:opacity-50"
        >
          {charge ? "…" : libelleBouton}
        </button>
      </form>

      <p className="text-center text-xs text-parchemin/50 mt-4">
        {lien.texte}{" "}
        <a href={lien.href} className="text-or hover:underline">
          {lien.href.replace("/", "")}
        </a>
      </p>
    </div>
  );
}
