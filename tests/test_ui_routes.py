"""Tests des routes/fonctions ajoutées pour l'UI (Phase 3-5).

Couvre sans service externe (aucun Qdrant, aucun LLM) :
- `GET /api/combat` (lister les rencontres) via TestClient sur dossiers temporaires ;
- `rag.retriever._sources()` (dérivation des citations structurées de fiches).

Lancement :
    python3 -m unittest tests.test_ui_routes -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "apps" / "api"))
sys.path.insert(0, str(RACINE / "packages"))


class TestListerCombat(unittest.TestCase):
    """`GET /api/combat` liste les rencontres persistées (resume)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="combat-list-")
        cls.dossier = Path(cls.tmp) / "combat"
        cls.dossier.mkdir(parents=True, exist_ok=True)
        os.environ["DND_API_KEY"] = "test-key"
        from fastapi.testclient import TestClient
        from jdr_api.main import app
        from dnd_perso import extract

        # `extract.COMBAT_DIR` est figé à l'import (constante partagée) : on le
        # repointe directement vers le dossier temporaire, indépendamment de
        # l'ordre d'import des autres modules de test.
        cls._combat_dir_origine = extract.COMBAT_DIR
        extract.COMBAT_DIR = cls.dossier

        cls.client = TestClient(app)
        cls.H = {"X-API-Key": "test-key"}

    @classmethod
    def tearDownClass(cls):
        from dnd_perso import extract

        extract.COMBAT_DIR = cls._combat_dir_origine

    def _ecrire(self, id_: str, **sur) -> None:
        dossier = self.dossier
        dossier.mkdir(parents=True, exist_ok=True)
        donnees = {
            "v": 1,
            "id": id_,
            "titre": sur.get("titre", f"Rencontre {id_}"),
            "active": sur.get("active", True),
            "tour": sur.get("tour", 1),
            "ordre": sur.get("ordre", []),
        }
        (dossier / f"rencontre-{id_}.json").write_text(
            json.dumps(donnees, ensure_ascii=False), encoding="utf-8"
        )

    def test_liste_vide_puis_peuplee(self):
        # Auth refusée sans clé.
        r = self.client.get("/api/combat")
        self.assertEqual(r.status_code, 200)
        self.assertIs(r.json()["ok"], False)

        self._ecrire("aaa", titre="Embuscade", ordre=[{"cle": "mon:0"}, {"cle": "pj:a"}])
        self._ecrire("bbb", titre="Siège", active=False, tour=4, ordre=[{"cle": "pj:a"}])

        r = self.client.get("/api/combat", headers=self.H)
        self.assertEqual(r.status_code, 200)
        corps = r.json()
        self.assertTrue(corps["ok"])
        self.assertEqual(corps["type"], "liste")
        par_id = {x["id"]: x for x in corps["rencontres"]}
        self.assertIn("aaa", par_id)
        self.assertIn("bbb", par_id)
        self.assertEqual(par_id["aaa"]["titre"], "Embuscade")
        self.assertEqual(par_id["aaa"]["nb_combattants"], 2)
        self.assertTrue(par_id["aaa"]["active"])
        self.assertFalse(par_id["bbb"]["active"])
        self.assertEqual(par_id["bbb"]["tour"], 4)


class TestSourcesRetriever(unittest.TestCase):
    """`_sources()` dérive les citations structurées des fiches retenues."""

    def setUp(self):
        from rag import retriever

        self._sources = retriever._sources

    def test_extrait_nom_source_edition(self):
        fiches = [
            {"nom": "Boule de feu", "contenu": "3e niveau...", "source": "SRD 5.2.1 p.170", "edition": "SRD 5.2.1"},
            {"nom": "Pas de source", "contenu": "...", "edition": "SRD 5.2.1"},
            {"nom": "Vide", "contenu": "   "},  # ignorée (contenu vide)
        ]
        out = self._sources(fiches)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], {"nom": "Boule de feu", "source": "SRD 5.2.1 p.170", "edition": "SRD 5.2.1"})
        # Sans « source », on retombe sur l'édition.
        self.assertEqual(out[1]["source"], "SRD 5.2.1")
        self.assertEqual(out[1]["nom"], "Pas de source")

    def test_vide_si_aucune_fiche(self):
        self.assertEqual(self._sources([]), [])


class TestEcrireCampagne(unittest.TestCase):
    """`POST /api/campagne/{id}/ecrire` persiste la trame d'une campagne ouverte
    (l'outil qui manquait) sans écraser le cadrage."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="campagne-ecrire-")
        cls.dossier = Path(cls.tmp) / "campagne"
        cls.dossier.mkdir(parents=True, exist_ok=True)
        os.environ["DND_API_KEY"] = "test-key"
        from fastapi.testclient import TestClient
        from jdr_api.main import app
        from dnd_perso import extract

        cls._campagne_dir_origine = extract.CAMPAGNE_DIR
        extract.CAMPAGNE_DIR = cls.dossier
        cls.client = TestClient(app)
        cls.H = {"X-API-Key": "test-key"}

    @classmethod
    def tearDownClass(cls):
        from dnd_perso import extract

        extract.CAMPAGNE_DIR = cls._campagne_dir_origine

    def test_ouvrir_puis_ecrire(self):
        # Ouverture = cadrage seul (coquille vide).
        r = self.client.post(
            "/api/campagne/ouvrir",
            json={"titre": "", "pj": ["Elminster"], "mode": "surprise",
                  "age_joueur": 45, "duree": "one-shot", "ton": "sombre"},
            headers=self.H,
        )
        self.assertTrue(r.json()["ok"])
        cid = r.json()["id"]
        self.assertFalse(r.json()["structure_valide"])  # trame absente

        # Écriture de la trame.
        r = self.client.post(
            f"/api/campagne/{cid}/ecrire",
            json={
                "titre": "Les Marges",
                "accroche": "La lettre d'Aldren.",
                "pnj": [{"nom": "Aldren", "objectif": "Survivre", "faille": "Lié", "attitude": "allié"}],
                "crochets": [
                    {"id": "c1", "titre": "Dette", "lie_a_pj": "Elminster"},
                    {"id": "c2", "titre": "Savoir", "lie_a_pj": "Elminster"},
                ],
                "defis": [{"nom": "Entrer", "approches": ["Forcer", "Ruse"]}],
            },
            headers=self.H,
        )
        corps = r.json()
        self.assertTrue(corps["ok"])
        self.assertEqual(corps["titre"], "Les Marges")
        self.assertTrue(corps["structure_valide"])
        # Cadrage préservé.
        self.assertEqual(corps["mode"], "surprise")
        self.assertEqual(corps["ton"], "sombre")
        # Persisté sur disque (relecture).
        r2 = self.client.get(f"/api/campagne/{cid}", headers=self.H)
        self.assertEqual(r2.json()["titre"], "Les Marges")
        self.assertEqual(len(r2.json()["crochets"]), 2)

    def test_ecrire_sans_cle_refuse(self):
        r = self.client.post("/api/campagne/abc/ecrire", json={"titre": "X"})
        self.assertFalse(r.json()["ok"])

    def test_ecrire_campagne_introuvable(self):
        r = self.client.post("/api/campagne/nexiste-pas/ecrire", json={"titre": "X"}, headers=self.H)
        self.assertFalse(r.json()["ok"])


if __name__ == "__main__":
    unittest.main()
