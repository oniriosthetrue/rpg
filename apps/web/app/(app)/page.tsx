import Link from "next/link";

// Page d'accueil du logiciel : présentation + accès rapide aux domaines.

const CARTE = [
  {
    href: "/campagne",
    icone: "📜",
    titre: "Nouvelle campagne",
    texte: "Crée un scénario guidé ou surprise, adapté à ton groupe de PJ.",
  },
  {
    href: "/chat",
    icone: "💬",
    titre: "Jouer",
    texte: "Rejoins le Maître du Jeu et vis ton aventure, tour après tour.",
  },
  {
    href: "/persos",
    icone: "🧝",
    titre: "Personnages",
    texte: "Crée et consulte tes fiches de personnages D&D 5.2.1.",
  },
  {
    href: "/combat",
    icone: "⚔️",
    titre: "Combat",
    texte: "Gère une rencontre : initiative, tours, jets et monstres.",
  },
];

export default function Accueil() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-12 space-y-10">
        <header className="text-center space-y-3">
          <h1 className="text-4xl font-bold text-or">MJ D&amp;D</h1>
          <p className="text-parchemin/70">
            Ton Maître de Jeu virtuel pour donjons &amp; dragons 5.2.1 (SRD).
            Il invente des scénarios, tient le monde en cohérence et arbitre les
            règles — toi, tu joues.
          </p>
        </header>

        <section className="grid gap-4 sm:grid-cols-2">
          {CARTE.map((c) => (
            <Link
              key={c.href}
              href={c.href}
              className="group rounded-xl border border-white/10 bg-black/20 p-5 transition hover:border-or/40 hover:bg-black/30"
            >
              <div className="text-3xl">{c.icone}</div>
              <div className="mt-2 font-semibold text-or group-hover:text-or">
                {c.titre}
              </div>
              <div className="mt-1 text-sm text-parchemin/60">{c.texte}</div>
            </Link>
          ))}
        </section>

        <footer className="text-center text-xs text-parchemin/40">
          Le moteur calcule les règles, le MJ invente l'histoire.
        </footer>
      </div>
    </div>
  );
}
