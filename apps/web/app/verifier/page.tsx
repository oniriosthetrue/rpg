"use client";

// Page de vérification d'email : lit le `token` de la query et appelle
// `/api/auth/verify`. Propose ensuite de se connecter.

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

function Verif() {
  const params = useSearchParams();
  const [etat, setEtat] = useState<"encours" | "ok" | "erreur">("encours");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setEtat("erreur");
      setMessage("Lien invalide (jeton manquant).");
      return;
    }
    fetch("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then((r) => r.json())
      .then((j) => {
        if (j.ok) {
          setEtat("ok");
          setMessage("Adresse confirmée ! Tu peux te connecter.");
        } else {
          setEtat("erreur");
          setMessage(j.erreur ?? "Lien invalide ou expiré.");
        }
      })
      .catch(() => {
        setEtat("erreur");
        setMessage("Serveur injoignable.");
      });
  }, [params]);

  return (
    <div className="w-full max-w-sm mx-auto p-6 text-center">
      <h1 className="text-2xl font-bold text-or mb-4">Vérification</h1>
      <p className={etat === "erreur" ? "text-red-400 text-sm" : "text-parchemin/80 text-sm"}>
        {etat === "encours" ? "Vérification en cours…" : message}
      </p>
      {etat === "ok" && (
        <Link href="/connexion" className="inline-block mt-6 rounded-lg bg-or/80 hover:bg-or text-encre font-semibold px-4 py-2">
          Se connecter
        </Link>
      )}
    </div>
  );
}

export default function PageVerifier() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-encre">
      <Suspense>
        <Verif />
      </Suspense>
    </main>
  );
}
