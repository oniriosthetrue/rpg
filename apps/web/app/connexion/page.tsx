import { Suspense } from "react";
import AuthForm from "@/components/AuthForm";

export default function PageConnexion() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-encre">
      <Suspense>
        <AuthForm
          action="login"
          titre="Connexion"
          sousTitre="Reprends ta partie là où tu l'as laissée."
          libelleBouton="Se connecter"
          lien={{ texte: "Pas encore de compte ?", href: "/inscription" }}
        />
      </Suspense>
    </main>
  );
}
