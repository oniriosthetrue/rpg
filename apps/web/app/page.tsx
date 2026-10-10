import { redirect } from "next/navigation";

// Racine du site → redirection vers le chat (préserve l'URL rpg.minervia.fr).
export default function Racine() {
  redirect("/chat");
}
