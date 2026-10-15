"""Tests du flux d'authentification par compte (email + mot de passe).

Couvre sans service externe (aucun Qdrant, aucun LLM, aucun SMTP) :
- inscription → connexion → accès à une route protégée ;
- isolation des données entre deux comptes (sous-dossiers distincts) ;
- rejet sans session / avec jeton invalide ;
- réinitialisation de mot de passe via jeton signé.

Lancement :
    python3 -m unittest tests.test_auth -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "apps" / "api"))
sys.path.insert(0, str(RACINE / "packages"))

# Environnement de test : secret + base SQLite + dossiers de données isolés.
_TMP = tempfile.mkdtemp(prefix="auth-test-")
os.environ.setdefault("AUTH_SECRET", "secret-de-test")
os.environ["DND_AUTH_DB"] = str(Path(_TMP) / "auth.db")
os.environ["DND_PERSO_DIR"] = str(Path(_TMP) / "perso")
os.environ["DND_COMBAT_DIR"] = str(Path(_TMP) / "combat")
os.environ["DND_CAMPAGNE_DIR"] = str(Path(_TMP) / "campagne")


class TestAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from jdr_api.main import app

        # `with` déclenche le lifespan → store.initialiser() (création de la table).
        cls._ctx = TestClient(app)
        cls.client = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def _inscrire(self, email: str) -> None:
        r = self.client.post("/api/auth/register", json={"email": email, "mot_de_passe": "motdepasse1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["type"], "inscrit")

    def _connecter(self, email: str) -> str:
        r = self.client.post("/api/auth/login", json={"email": email, "mot_de_passe": "motdepasse1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["type"], "connecte")
        return r.json()["session"]

    def test_inscription_puis_connexion(self):
        self._inscrire("alice@exemple.fr")
        session = self._connecter("alice@exemple.fr")
        r = self.client.get("/api/auth/me", headers={"X-Session": session})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["email"], "alice@exemple.fr")

    def test_email_en_double_refuse(self):
        self._inscrire("double@exemple.fr")
        r = self.client.post("/api/auth/register", json={"email": "double@exemple.fr", "mot_de_passe": "motdepasse1"})
        self.assertIs(r.json()["ok"], False)

    def test_mot_de_passe_trop_court_refuse(self):
        r = self.client.post("/api/auth/register", json={"email": "court@exemple.fr", "mot_de_passe": "abc"})
        self.assertIs(r.json()["ok"], False)

    def test_mauvais_mot_de_passe(self):
        self._inscrire("mauvais@exemple.fr")
        r = self.client.post("/api/auth/login", json={"email": "mauvais@exemple.fr", "mot_de_passe": "mauvaismdp"})
        self.assertIs(r.json()["ok"], False)

    def test_route_protegee_sans_session(self):
        r = self.client.get("/api/personnages")
        self.assertEqual(r.status_code, 401)

    def test_jeton_invalide_refuse(self):
        r = self.client.get("/api/personnages", headers={"X-Session": "pas-un-jeton"})
        self.assertEqual(r.status_code, 401)

    def test_isolation_entre_comptes(self):
        self._inscrire("u1@exemple.fr")
        self._inscrire("u2@exemple.fr")
        t1 = self._connecter("u1@exemple.fr")
        t2 = self._connecter("u2@exemple.fr")
        # Chaque session doit résoudre un sous-dossier de données distinct.
        from dnd_perso import extract

        tok1 = extract.definir_utilisateur("u1")
        dir1 = extract.PERSO_DIR
        extract.restaurer_utilisateur(tok1)
        tok2 = extract.definir_utilisateur("u2")
        dir2 = extract.PERSO_DIR
        extract.restaurer_utilisateur(tok2)
        self.assertNotEqual(dir1, dir2)
        # Les deux listes de persos sont indépendantes et vides.
        l1 = self.client.get("/api/personnages", headers={"X-Session": t1}).json()
        l2 = self.client.get("/api/personnages", headers={"X-Session": t2}).json()
        self.assertEqual(l1.get("personnages"), [])
        self.assertEqual(l2.get("personnages"), [])

    def test_reinitialisation_mot_de_passe(self):
        from auth import security, store

        self._inscrire("reset@exemple.fr")
        jeton = security.signer({"uid": "reset@exemple.fr", "but": "reset"}, os.environ["AUTH_SECRET"], 3600)
        store.definir_token_reset("reset@exemple.fr", jeton)
        r = self.client.post("/api/auth/reset", json={"token": jeton, "mot_de_passe": "noueaumotdepasse"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["type"], "reinitialise")
        # Ancien mdp refusé, nouveau accepté.
        r = self.client.post("/api/auth/login", json={"email": "reset@exemple.fr", "mot_de_passe": "motdepasse1"})
        self.assertIs(r.json()["ok"], False)
        r = self.client.post("/api/auth/login", json={"email": "reset@exemple.fr", "mot_de_passe": "noueaumotdepasse"})
        self.assertEqual(r.json()["type"], "connecte")


if __name__ == "__main__":
    unittest.main()
