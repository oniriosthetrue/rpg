"use client";

// Réinitialisation du mot de passe. Deux modes :
// - sans `token` dans l'URL → demande de réinitialisation (saisie email) ;
// - avec `token` → saisie du nouveau mot de passe.

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";

function Reinit() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token");

  const [email, setEmail] = useState("");
  const [mdp, setMdp] = useState("");
  const [erreur, setErreur] = useState("");
  const [info, setInfo] = useState("");
  const [charge, setCharge] = useState(false);

  useEffect(() => setErreur(""), [token]);

  async function demander(e: React.FormEvent) {
    e.preventDefault();
    setErreur("");
    setCharge(true);
    try {
      const r = await fetch("/api/auth/forgot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const j = await r.json();
      setInfo("Si un compte existe avec cet email, un lien de réinitialisation a été envoyé.");
      setCharge(false);
      void j;
    } catch {
      setErreur("Serveur injoignable.");
      setCharge(false);
    }
  }

  async function reinitialiser(e: React.FormEvent) {
    e.preventDefault();
    setErreur("");
    if (mdp.length < 8) {
      setErreur("Le mot de passe doit faire au moins 8 caractères.");
      return;
    }
    setCharge(true);
    try {
      const r = await fetch("/api/auth/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, mot_de_passe: mdp }),
      });
      const j = await r.json();
      if (j.ok) {
        router.replace("/connexion");
      } else {
        setErreur(j.erreur ?? "Lien invalide ou expiré.");
        setCharge(false);
      }
    } catch {
      setErreur("Serveur injoignable.");
      setCharge(false);
    }
  }

  return (
    <div className="w-full max-w-sm mx-auto p-6">
      <h1 className="text-2xl font-bold text-or mb-4 text-center">
        {token ? "Nouveau mot de passe" : "Mot de passe oublié"}
      </h1>

      {token ? (
        <form onSubmit={reinitialiser} className="space-y-4">
          <input
            type="password"
            required
            minLength={8}
            placeholder="Nouveau mot de passe"
            autoComplete="new-password"
            value={mdp}
            onChange={(e) => setMdp(e.target.value)}
            className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm focus:border-or/60 focus:outline-none"
          />
          {erreur && <div className="text-red-400 text-xs">{erreur}</div>}
          <button
            type="submit"
            disabled={charge}
            className="w-full rounded-lg bg-or/80 hover:bg-or text-encre font-semibold py-2 disabled:opacity-50"
          >
            {charge ? "…" : "Enregistrer"}
          </button>
        </form>
      ) : (
        <form onSubmit={demander} className="space-y-4">
          <input
            type="email"
            required
            placeholder="Ton email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm focus:border-or/60 focus:outline-none"
          />
          {erreur && <div className="text-red-400 text-xs">{erreur}</div>}
          {info && <div className="text-emerald-400 text-xs">{info}</div>}
          <button
            type="submit"
            disabled={charge}
            className="w-full rounded-lg bg-or/80 hover:bg-or text-encre font-semibold py-2 disabled:opacity-50"
          >
            {charge ? "…" : "Envoyer le lien"}
          </button>
        </form>
      )}

      <p className="text-center text-xs text-parchemin/50 mt-4">
        <Link href="/connexion" className="text-or hover:underline">
          Retour à la connexion
        </Link>
      </p>
    </div>
  );
}

export default function PageReinitialiser() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-encre">
      <Suspense>
        <Reinit />
      </Suspense>
    </main>
  );
}
