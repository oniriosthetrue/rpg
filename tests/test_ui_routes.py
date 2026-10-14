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


class TestCascadeSuppressionCampagne(unittest.TestCase):
    """Supprimer une campagne supprime aussi les combats rattachés (via
    `campagne_id`), et uniquement ceux-là."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cascade-")
        cls.dossier_campagne = Path(cls.tmp) / "campagne"
        cls.dossier_combat = Path(cls.tmp) / "combat"
        cls.dossier_perso = Path(cls.tmp) / "perso"
        cls.dossier_campagne.mkdir(parents=True, exist_ok=True)
        cls.dossier_combat.mkdir(parents=True, exist_ok=True)
        cls.dossier_perso.mkdir(parents=True, exist_ok=True)
        os.environ["DND_API_KEY"] = "test-key"
        from fastapi.testclient import TestClient
        from jdr_api.main import app
        from dnd_perso import extract

        # Le router combat exige ≥1 PJ (lu depuis une fiche) et, quand la rencontre
        # est rattachée à une campagne, une zone dangereuse déclarée : on fournit les
        # deux pour que la cascade s'exerce dans un état licite.
        (cls.dossier_perso / "Heros.json").write_text(
            json.dumps({"nom": "Heros", "classe": "Guerrier", "niveau": 1,
                        "carac": {"Force": 16, "Dextérité": 14, "Constitution": 14}},
                       ensure_ascii=False),
            encoding="utf-8",
        )

        cls._campagne_dir_origine = extract.CAMPAGNE_DIR
        cls._combat_dir_origine = extract.COMBAT_DIR
        cls._perso_dir_origine = extract.PERSO_DIR
        extract.CAMPAGNE_DIR = cls.dossier_campagne
        extract.COMBAT_DIR = cls.dossier_combat
        extract.PERSO_DIR = cls.dossier_perso
        cls.client = TestClient(app)
        cls.H = {"X-API-Key": "test-key"}

    @classmethod
    def tearDownClass(cls):
        from dnd_perso import extract

        extract.CAMPAGNE_DIR = cls._campagne_dir_origine
        extract.COMBAT_DIR = cls._combat_dir_origine
        extract.PERSO_DIR = cls._perso_dir_origine

    def _declarer_zone(self, campagne_id: str) -> None:
        """Déclare sur la campagne une zone dangereuse où la rencontre (Gobelin +
        Orc) est planifiée — sinon le garde « zone » du router combat refuse l'ouverture."""
        r = self.client.post(
            f"/api/campagne/{campagne_id}/ecrire",
            json={
                "lieux": [{
                    "nom": "Antre",
                    "zone": "dangereuse",
                    "rencontre": {"titre": "Raid", "monstres": [
                        {"nom": "Gobelin", "nb": 1}, {"nom": "Orc", "nb": 1}]},
                }],
            },
            headers=self.H,
        )
        self.assertTrue(r.json()["ok"], r.json())

    def _ouvrir_combat(self, campagne_id: str, cid: str) -> str:
        r = self.client.post(
            "/api/combat/ouvrir",
            json={
                "id": cid,
                "campagne_id": campagne_id,
                "titre": "Escarmouche",
                "combattants": [
                    {"type": "pj", "nom": "Heros"},
                    {"type": "monstre", "nom": "Gobelin", "pv": 7, "ca": 15,
                     "attaque": 4, "degats": "1d6+2", "mod_degats": 2, "init_bonus": 2},
                    {"type": "monstre", "nom": "Orc", "pv": 11, "ca": 13,
                     "attaque": 5, "degats": "1d12", "mod_degats": 3, "init_bonus": 1},
                ],
            },
            headers=self.H,
        )
        self.assertTrue(r.json()["ok"], r.json())
        return r.json()["id"]

    def test_supprimer_campagne_supprime_ses_combats(self):
        # Campagne A + deux combats rattachés ; campagne B + un combat rattaché.
        ra = self.client.post("/api/campagne/ouvrir", json={"id": "casc-a", "titre": "A"}, headers=self.H)
        cid_a = ra.json()["id"]
        ra = self.client.post("/api/campagne/ouvrir", json={"id": "casc-b", "titre": "B"}, headers=self.H)
        cid_b = ra.json()["id"]
        # Zones dangereuses déclarées pour A et B (les combats y sont rattachés).
        self._declarer_zone(cid_a)
        self._declarer_zone(cid_b)

        combat_a1 = self._ouvrir_combat(cid_a, "ca1")
        combat_a2 = self._ouvrir_combat(cid_a, "ca2")
        combat_b1 = self._ouvrir_combat(cid_b, "cb1")
        combat_orphelin = self._ouvrir_combat("", "co1")  # hors campagne

        # Le champ campagne_id est bien persisté.
        etat = self.client.get(f"/api/combat/{combat_a1}", headers=self.H).json()
        self.assertEqual(etat["campagne_id"], cid_a)

        # Suppression de la campagne A → ses 2 combats disparaissent, pas ceux de B ni l'orphelin.
        r = self.client.delete(f"/api/campagne/{cid_a}", headers=self.H)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(sorted(r.json()["combats_supprimes"]), sorted([combat_a1, combat_a2]))

        self.assertFalse((self.dossier_combat / f"rencontre-{combat_a1}.json").exists())
        self.assertFalse((self.dossier_combat / f"rencontre-{combat_a2}.json").exists())
        self.assertTrue((self.dossier_combat / f"rencontre-{combat_b1}.json").exists())
        self.assertTrue((self.dossier_combat / f"rencontre-{combat_orphelin}.json").exists())

    def test_supprimer_sans_cle_refuse(self):
        r = self.client.delete("/api/campagne/abc")
        self.assertFalse(r.json()["ok"])


if __name__ == "__main__":
    unittest.main()
