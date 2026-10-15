import { Suspense } from "react";
import AuthForm from "@/components/AuthForm";

export default function PageInscription() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-encre">
      <Suspense>
        <AuthForm
          action="register"
          titre="Inscription"
          sousTitre="Crée ton compte MJ — l'accès est libre."
          libelleBouton="Créer mon compte"
          lien={{ texte: "Déjà un compte ?", href: "/connexion" }}
        />
      </Suspense>
    </main>
  );
}
