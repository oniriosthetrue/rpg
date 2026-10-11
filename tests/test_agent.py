"""Tests d'intégration de l'agent MJ (Phase 4).

Trois garanties « contrat MJ », testées de façon **déterministe** (modèle
factice `FunctionModel`, aucun appel réseau au LLM) :

1. **Cerveau règles** — l'agent délègue tout ce qui est chiffré à un outil
   (création, liste, combat) et ne calcule rien lui-même : on vérifie que le
   bon outil est appelé avec les bons arguments, et que le JSON du moteur
   remonte tel quel.
2. **Anti-métajeu (post-traitement)** — `postprocess.anti_meta` masque les
   stats de monstre (CA/PV en bloc), corrige l'emphase collée, retire les
   anciennes étiquettes de bloc.
3. **RAG / citations** — le contexte injecté exige la citation et borne le
   modèle (« n'invente rien hors de ces fiches ») ; format `Source : …`.

Lancement :
    python3 -m unittest tests.test_agent -v
"""

from __future__ import annotations

import os
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "apps" / "api"))
sys.path.insert(0, str(RACINE / "packages"))

# Environnement minimal pour importer l'agent sans service externe.
os.environ.setdefault("DND_CORPUS_DIR", str(RACINE / "packages" / "corpus" / "srd-5.2.1"))
os.environ.setdefault("DND_PERSO_DIR", str(RACINE / "data-perso"))
os.environ.setdefault("DND_COMBAT_DIR", str(RACINE / "data-combat"))
os.environ.setdefault("DND_CAMPAGNE_DIR", str(RACINE / "data-campagne"))

from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import FunctionModel  # noqa: E402

from agent.tools import Deps  # noqa: E402
from postprocess import anti_meta  # noqa: E402


# ─── Helpers de modèle factice ──────────────────────────────────────────────

def _a_deja_reponse_outil(messages) -> bool:
    """Vrai si un tool-return existe déjà dans l'historique (donc 2e tour)."""
    for m in messages:
        for p in getattr(m, "parts", []):
            if getattr(p, "part_kind", "") == "tool-return":
                return True
    return False


# ─── 1. Cerveau règles : délégation aux outils ───────────────────────────────

class TestDlegationOutils(unittest.TestCase):
    def _lancer(self, outil, args_1er_tour, prompt="…"):
        """Agent factice : 1er tour = appel d'outil avec `args`, puis texte."""
        appelee: list[tuple[str, Any]] = []

        def fake(messages, info):
            if not _a_deja_reponse_outil(messages):
                appelee.append((outil.__name__, args_1er_tour))
                return ModelResponse(
                    parts=[ToolCallPart(outil.__name__, args_1er_tour)]
                )
            return ModelResponse(parts=[TextPart("OK raconté.")])

        agent = Agent(FunctionModel(fake), deps_type=Deps)
        # Enregistrer le VRAI outil (wrappeur moteur) pour vérifier l'exécution.
        from agent import tools

        if outil in tools.OUTILS_CTX:
            agent.tool(outil)
        else:
            agent.tool_plain(outil)
        res = agent.run_sync(prompt, deps=Deps(chat_id="test"))
        return res, appelee

    def test_lister_delegue_au_moteur(self):
        from agent.tools import lister_les_personnages

        res, appelee = self._lancer(lister_les_personnages, {})
        # L'outil a été appelé par le modèle…
        self.assertEqual(appelee[0][0], "lister_les_personnages")
        # …et le JSON du moteur (enveloppe v1) est revenu dans l'historique.
        msgs = res.all_messages_json().decode()
        self.assertIn('"type"', msgs)
        self.assertIn("liste", msgs)

    def test_creation_transmet_le_chat_id(self):
        """Le `chat_id` des deps doit atteindre le moteur (session de création)."""
        from agent.tools import nouveau_personnage

        def fake(messages, info):
            if not _a_deja_reponse_outil(messages):
                return ModelResponse(parts=[ToolCallPart("nouveau_personnage", {})])
            return ModelResponse(parts=[TextPart("Question posée.")])

        agent = Agent(FunctionModel(fake), deps_type=Deps)
        agent.tool(nouveau_personnage)
        res = agent.run_sync("je crée un perso", deps=Deps(chat_id="session-42"))
        # Démarrage de création → le moteur renvoie une question (etape classe).
        blob = res.all_messages_json().decode()
        self.assertIn("question", blob)
        self.assertIn("classe", blob)

    def test_ouvrir_combat_recoit_l_ordre(self):
        """`ouvrir_un_combat` renvoie l'ordre d'initiative calculé par le serveur."""
        from agent.tools import ouvrir_un_combat

        args = {
            "combattants": [
                {"type": "monstre", "nom": "Gobelin", "pv": 7, "ca": 15,
                 "attaque": 4, "degats": "1d6+2", "mod_degats": 2, "init_bonus": 2},
                {"type": "monstre", "nom": "Orc", "pv": 11, "ca": 13,
                 "attaque": 5, "degats": "1d12", "mod_degats": 3, "init_bonus": 1},
            ],
            "titre": "Embuscade",
        }

        def fake(messages, info):
            if not _a_deja_reponse_outil(messages):
                return ModelResponse(parts=[ToolCallPart("ouvrir_un_combat", args)])
            return ModelResponse(parts=[TextPart("Combat ouvert.")])

        agent = Agent(FunctionModel(fake), deps_type=Deps)
        agent.tool(ouvrir_un_combat)
        res = agent.run_sync("que le combat commence", deps=Deps())
        blob = res.all_messages_json().decode()
        # Le serveur a calculé l'initiative : ordre + identifiant de rencontre présents.
        self.assertIn("ordre", blob)
        self.assertIn("initiative", blob)
        self.assertIn('"id"', blob)


# ─── 2. Anti-métajeu : post-traitement ───────────────────────────────────────

class TestAntiMeta(unittest.TestCase):
    def test_masque_ca_bloc_stats(self):
        out = anti_meta.nettoyer("Le gobelin a CA : 15 et attaque +4.")
        self.assertNotIn("15", out)
        self.assertIn("CA", out)  # le libellé reste, seul le chiffre est masqué

    def test_masque_pv_bloc_stats(self):
        out = anti_meta.nettoyer("Ses points de vie : 7 sont bas.")
        self.assertNotIn("7", out)

    def test_ne_masque_pas_valeur_differentielle(self):
        # « tu perds 5 PV » n'est PAS un bloc de stats → ne doit pas être masqué.
        out = anti_meta.nettoyer("Tu perds 5 PV.")
        self.assertIn("5", out)

    def test_corrige_emphase_collee(self):
        out = anti_meta.nettoyer("le du**Royaume** de l'ombre")
        self.assertIn("du **Royaume**", out)

    def test_retire_etiquettes_bloc(self):
        out = anti_meta.nettoyer("[MÉCANIQUE]\nTu fais un jet.\n[NARRATION]\nLe vent souffle.")
        self.assertNotIn("MÉCANIQUE", out)
        self.assertNotIn("NARRATION", out)

    def test_retire_menu_bloc_sections(self):
        # Un « menu » d'options (amorce « Tu peux : » + sections emoji) doit être
        # retiré, la question de clôture (« Tu fais quoi ? ») conservée.
        texte = (
            "Tu es dans l'archive. Tu peux :\n\n"
            "🔍 Explorer la salle :\n\nExaminer la marque au sol.\n"
            "Fouiller les décombres.\n\n⚡ Autres :\n\nLancer un sort.\n\n"
            "---\n\nTu fais quoi ?"
        )
        out = anti_meta.nettoyer(texte)
        self.assertNotIn("Explorer la salle", out)
        self.assertNotIn("Lancer un sort", out)
        self.assertIn("Tu fais quoi ?", out)

    def test_retire_tableau_menu(self):
        texte = (
            "Voici tes options :\n\n"
            "| Option | Type de jet |\n|---|---|\n"
            "| Examiner la marque | Arcanes +3 |\n| Chercher | Perception +0 |\n\n"
            "Tu es seul."
        )
        out = anti_meta.nettoyer(texte)
        self.assertNotIn("Type de jet", out)
        self.assertNotIn("Arcanes +3", out)

    def test_garde_tableau_inventaire(self):
        # Un tableau légitime (inventaire) ne doit PAS être retiré.
        texte = "Ton inventaire :\n\n| Objet | Qté |\n|---|---|\n| Dague | 2 |\n"
        out = anti_meta.nettoyer(texte)
        self.assertIn("Dague", out)

    def test_retire_synthese_gras(self):
        # Un bloc « Ce que tu retiens » (amorce en gras) doit être retiré, la
        # narration qui précède et la question de clôture conservées.
        texte = (
            "Tu observes la brûlure sur le granite.\n\n"
            "**Ce que tu retiens :**\n"
            "Le voleur a utilisé un sort d'Évocation majeur.\n"
            "C'est la signature d'un praticien particulier.\n\n"
            "Que fais-tu ?"
        )
        out = anti_meta.nettoyer(texte)
        self.assertIn("Tu observes la brûlure", out)
        self.assertNotIn("Ce que tu retiens", out)
        self.assertNotIn("Évocation majeur", out)
        self.assertIn("Que fais-tu ?", out)

    def test_retire_synthese_titre(self):
        # Un titre « ## Résumé » retire le bloc jusqu'au titre suivant (conservé).
        texte = (
            "La salle est saccagée.\n\n"
            "## Résumé\n"
            "Le Codex a disparu.\n\n"
            "## La suite\n"
            "Un couloir descend vers le nord.\n"
        )
        out = anti_meta.nettoyer(texte)
        self.assertIn("La salle est saccagée", out)
        self.assertNotIn("Le Codex a disparu", out)
        self.assertIn("## La suite", out)
        self.assertIn("Un couloir descend", out)

    def test_garde_resume_dans_narration(self):
        # Le mot « résumé » en pleine phrase (pas une amorce) ne doit rien retirer.
        texte = "Le scribe a laissé un résumé des comptes sur la table. Que fais-tu ?"
        out = anti_meta.nettoyer(texte)
        self.assertIn("résumé des comptes", out)

    def test_retire_synthese_vous_savez(self):
        # Amorce en gras au vousvoiement (« Ce que vous savez maintenant : ») + liste
        # à puces, encadrée de `---`. Le bloc doit disparaître, la suite rester.
        texte = (
            "La brûlure vous donne une certitude.\n\n"
            "---\n\n"
            "**Ce que vous savez maintenant :**\n\n"
            "- Cael a fui avec le Codex.\n"
            "- L'encre est encore humide.\n"
            "---\n\n"
            "Vous êtes au bord du gouffre.\n\nQue faites-vous ?"
        )
        out = anti_meta.nettoyer(texte)
        self.assertIn("La brûlure vous donne", out)
        self.assertNotIn("Ce que vous savez", out)
        self.assertNotIn("Cael a fui", out)
        self.assertIn("Vous êtes au bord", out)
        self.assertIn("Que faites-vous ?", out)


# ─── 3. RAG : contexte borné + citation ──────────────────────────────────────

class TestContexteRag(unittest.TestCase):
    def test_en_tete_borne_et_exige_citation(self):
        from rag import retriever, embeddings, qdrant_store
        from rag import corpus

        fiches = corpus.iterer_fiches()
        if not fiches:
            self.skipTest("corpus absent")
        # `rechercher` renvoie des payloads (dicts), pas des Fiche : cf. retriever.
        payload = fiches[0].payload()

        # On court-circuite embeddings + Qdrant (pas de réseau pendant les tests).
        emb_orig, rech_orig = embeddings.embed_un, qdrant_store.rechercher
        retriever.embeddings.embed_un = lambda q: [0.0]
        retriever.qdrant_store.rechercher = lambda v, top_k=None: [payload]
        try:
            ctx = retriever.recuperer_contexte("test")
        finally:
            retriever.embeddings.embed_un = emb_orig
            retriever.qdrant_store.rechercher = rech_orig

        self.assertIn("Base de connaissances SRD", ctx)
        self.assertIn("n'invente rien", ctx)
        self.assertIn("Source", ctx)
        self.assertIn(payload["nom"], ctx)

    def test_contexte_vide_si_aucune_fiche(self):
        from rag import retriever

        emb_orig, rech_orig = retriever.embeddings.embed_un, retriever.qdrant_store.rechercher
        retriever.embeddings.embed_un = lambda q: [0.0]
        retriever.qdrant_store.rechercher = lambda v, top_k=None: []
        try:
            self.assertEqual(retriever.recuperer_contexte("x"), "")
        finally:
            retriever.embeddings.embed_un = emb_orig
            retriever.qdrant_store.rechercher = rech_orig

    def test_hybride_retient_un_nom_exact_absent_du_top_vectoriel(self):
        from rag import corpus, keyword_search, retriever

        cape = next(
            fiche
            for fiche in corpus.iterer_fiches()
            if fiche.id == "objets/cape-dinvisibilite"
        ).payload()
        resultats_lexicaux = keyword_search.rechercher("Cape d'invisibilité", 5)
        self.assertEqual(resultats_lexicaux[0]["id"], cape["id"])
        self.assertTrue(resultats_lexicaux[0]["_keyword_exact_name"])

        bruit_vectoriel = {
            "id": "objets/amulette-de-protection",
            "nom": "Amulette de protection",
            "source": "SRD 5.2.1",
            "contenu": "Une amulette protectrice.",
        }
        emb_orig, rech_orig = (
            retriever.embeddings.embed_un,
            retriever.qdrant_store.rechercher,
        )
        retriever.embeddings.embed_un = lambda q: [0.0]
        retriever.qdrant_store.rechercher = lambda v, top_k=None: [
            bruit_vectoriel
        ]
        try:
            contexte = retriever.recuperer_contexte("Cape d'invisibilité")
        finally:
            retriever.embeddings.embed_un = emb_orig
            retriever.qdrant_store.rechercher = rech_orig

        self.assertIn(cape["nom"], contexte)
        self.assertIn(cape["contenu"], contexte)
        premier_bloc = contexte.split("\n\n---\n\n", maxsplit=1)[0]
        self.assertIn(f"\n\n### {cape['nom']}", premier_bloc)


# ─── 4. Hook de capture : jets de dés lancés par le MJ ───────────────────────

class TestCapture(unittest.TestCase):
    def setUp(self):
        from postprocess import capture

        self.capture = capture

    def test_detecte_total_resolu(self):
        self.assertTrue(self.capture.detecter_jet_auto("## Jet d'Investigation (Intelligence) : **d20 + 4 = 17** ✓"))

    def test_detecte_resultat_coché(self):
        self.assertTrue(self.capture.detecter_jet_auto("Le dé roule et fait = 19 ✓"))

    def test_detecte_anonce_de_jet(self):
        self.assertTrue(self.capture.detecter_jet_auto("Je lance un d20 pour ton attaque."))

    def test_detecte_resultat_joueur(self):
        self.assertTrue(self.capture.detecter_jet_auto("Tu obtiens 23, c'est suffisant."))

    def test_ne_detecte_pas_une_demande_de_lancer(self):
        # Une simple invitation à lancer (aucun total) ne doit PAS déclencher.
        texte = "Lance ton jet d'attaque : d20 + ton modificateur de Force, puis dis-moi le résultat."
        self.assertFalse(self.capture.detecter_jet_auto(texte))

    def test_ne_detecte_pas_la_narration(self):
        # « tu fais 3 pas », « tu obtiens le silence » (sans nombre) : narration, pas un dé.
        self.assertFalse(self.capture.detecter_jet_auto("Tu fais trois pas vers la porte."))
        self.assertFalse(self.capture.detecter_jet_auto("Tu avances et observes la salle."))

    def test_joueur_a_donne_un_de(self):
        self.assertTrue(self.capture.le_joueur_a_donne_un_de("Je fais 16"))
        self.assertFalse(self.capture.le_joueur_a_donne_un_de("J'inspecte la pièce"))

    def test_repli_retire_les_lignes_de_jet(self):
        texte = "La scène continue.\n## Jet : **d20 + 4 = 17** ✓\nTu avances prudemment."
        out = self.capture.retirer_jet_resolu(texte)
        self.assertNotIn("= 17", out)
        self.assertIn("Tu avances prudemment.", out)
        self.assertIn("La scène continue.", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
