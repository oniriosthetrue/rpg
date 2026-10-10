"""Tests de la création de personnage D&D 5e (SRD 5.2.1).

Lancement :
    python3 -m unittest tests.test_dnd_perso -v
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

# Assurer l'accès au package `dnd_perso` quand on lance depuis la racine.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dnd_perso import creation  # noqa: E402
from dnd_perso import export  # noqa: E402
from dnd_perso import extract  # noqa: E402
from dnd_perso import models  # noqa: E402


class TestExtract(unittest.TestCase):
    def test_charger_tout_complet(self):
        donnees = extract.charger_tout()
        self.assertEqual(len(donnees["classes"]), 12)
        self.assertEqual(len(donnees["historiques"]), 4)
        self.assertEqual(len(donnees["especes"]), 9)
        self.assertEqual(len(donnees["alignements"]), 9)
        self.assertEqual(len(donnees["babioles"]), 100)
        # Cantrips : noms en français, non vides.
        for classe, sorts in donnees["cantrips"].items():
            self.assertTrue(sorts, f"cantrips vides pour {classe}")
            for s in sorts:
                self.assertTrue(s.strip())

    def test_sorts_1_noms_francais(self):
        donnees = extract.charger_tout()
        for classe, sorts in donnees["sorts_1"].items():
            for s in sorts:
                self.assertTrue(s.strip())
                self.assertTrue(any(c.isupper() for c in s))


class TestDice(unittest.TestCase):
    def test_roll_d20(self):
        rng = random.Random(1)
        for _ in range(50):
            v = __import__("dnd_perso.dice", fromlist=["dice"]).roll("1d20", rng)
            self.assertGreaterEqual(v, 1)
            self.assertLessEqual(v, 20)

    def test_roll_3d6_kh3(self):
        from dnd_perso import dice
        rng = random.Random(7)
        v = dice.roll("3d6kh3", rng)
        self.assertGreaterEqual(v, 3)
        self.assertLessEqual(v, 18)

    def test_roll_invalide(self):
        from dnd_perso import dice
        with self.assertRaises(ValueError):
            dice.roll("2d0")

    def test_roll_d100_babiole(self):
        from dnd_perso import dice
        rng = random.Random(3)
        table = [(1, "a"), (50, "b"), (100, "c")]
        tirage, nom = dice.roll_d100(table, rng)
        self.assertGreaterEqual(tirage, 1)
        self.assertIn(nom, ("a", "b", "c"))


class TestCaracteristiques(unittest.TestCase):
    def test_standard(self):
        c = models.Caracteristiques.depuis_liste(list(extract.ARRAY_STANDARD))
        self.assertEqual(c.valeurs(), [15, 14, 13, 12, 10, 8])
        self.assertEqual(c.mod_for(), 2)
        self.assertEqual(c.mod_char(), -1)

    def test_mod_negatif(self):
        c = models.Caracteristiques.depuis_liste([8, 8, 8, 8, 8, 8])
        self.assertEqual(c.mod_for(), -1)

    def test_mod_zero(self):
        c = models.Caracteristiques.depuis_liste([10, 10, 10, 10, 10, 10])
        self.assertEqual(c.mod_for(), 0)


class TestCreationAuto(unittest.TestCase):
    def test_10_personnages_valides(self):
        donnees = extract.charger_tout()
        for graine in range(10):
            rng = random.Random(graine)
            p = creation.creer_automatiquement(rng, donnees)
            with self.subTest(seed=graine):
                # Nom non vide.
                self.assertTrue(p.nom.strip())
                # Espèce / classe / historique connus.
                self.assertIn(p.espece, donnees["especes"])
                self.assertIn(p.classe, donnees["classes"])
                self.assertIn(p.historique, donnees["historiques"])
                # Caractéristiques bornées et modificateurs corrects.
                for v in p.carac.valeurs():
                    self.assertGreaterEqual(v, 8)
                    self.assertLessEqual(v, 20)
                    self.assertEqual(models.Caracteristiques.mod(v), (v - 10) // 2)
                # PV = de_vie + mod Con.
                self.assertEqual(p.pv, p.de_vie + p.carac.mod_con())
                # Compétences : au plus nb_competences + historique.
                self.assertGreaterEqual(len(p.competences), 1)
                # Sorts : les lanceurs ont des sorts, les autres non.
                info = donnees["classes"][p.classe]
                if info.get("lanceur"):
                    self.assertTrue(p.sorts)
                else:
                    self.assertEqual(p.sorts, [])
                # Babiole non vide.
                self.assertTrue(p.babiole.strip())
                # Alignement valide.
                self.assertIn(p.alignement, donnees["alignements"])

    def test_lanceur_a_des_sorts(self):
        donnees = extract.charger_tout()
        rng = random.Random(123)
        p = creation.creer_automatiquement(rng, donnees)
        if donnees["classes"][p.classe].get("lanceur"):
            self.assertTrue(all(s.strip() for s in p.sorts))


class TestExport(unittest.TestCase):
    def test_export_md_et_json(self):
        donnees = extract.charger_tout()
        p = creation.creer_automatiquement(random.Random(99), donnees)
        md = export.vers_fiche(p)
        self.assertIn("<<<FICHE>>>", md)
        self.assertIn("<<<CONTENU>>>", md)
        self.assertIn("<<<FIN>>>", md)
        self.assertIn(p.nom, md)
        json_str = export.vers_json(p)
        self.assertIn('"nom"', json_str)
        self.assertIn(p.nom, json_str)

    def test_sauvegarde_ecrit_fichiers(self):
        import tempfile
        donnees = extract.charger_tout()
        p = creation.creer_automatiquement(random.Random(5), donnees)
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            md_path, json_path = export.sauvegarder(p, dossier=dossier)
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            contenu = md_path.read_text(encoding="utf-8")
            self.assertIn("<<<FICHE>>>", contenu)


class TestTableDesJets(unittest.TestCase):
    """La table des bonus de jet doit être pré-calculée (le MJ la lit, ne calcule pas)."""

    def _barde(self):
        return models.Personnage(
            nom="Test",
            classe="Barde",
            carac=models.Caracteristiques(
                force=8, dexterite=14, constitution=12,
                intelligence=10, sagesse=11, charisme=16,
            ),
            competences=[
                models.Competence("Tromperie", True),
                models.Competence("Persuasion", True),
            ],
            bonus_maitrise=2,
        )

    def test_competence_maitrisee_inclut_bonus(self):
        jets = self._barde().table_des_jets()
        # Charisme 16 -> mod +3, Tromperie maîtrisée -> +2 = +5.
        self.assertEqual(jets["competences"]["Tromperie"], 5)
        self.assertEqual(jets["competences"]["Persuasion"], 5)

    def test_competence_non_maitrisee_mod_seul(self):
        jets = self._barde().table_des_jets()
        # Sagesse 11 -> mod +0, Perception non maîtrisée -> +0.
        self.assertEqual(jets["competences"]["Perception"], 0)

    def test_sauvegarde_de_classe_inclut_bonus(self):
        jets = self._barde().table_des_jets()
        # Barde : sauvegardes Dextérité + Charisme.
        self.assertEqual(jets["sauvegardes"]["Charisme"], 5)  # +3 +2
        self.assertEqual(jets["sauvegardes"]["Dextérité"], 4)  # +2 +2

    def test_sauvegarde_hors_classe_mod_seul(self):
        jets = self._barde().table_des_jets()
        # Force 8 -> mod -1, non sauvegarde de Barde -> -1.
        self.assertEqual(jets["sauvegardes"]["Force"], -1)

    def test_toutes_competences_et_sauvegardes_presentes(self):
        jets = self._barde().table_des_jets()
        self.assertEqual(set(jets["competences"]), set(models.LISTE_COMPETENCES))
        self.assertEqual(set(jets["sauvegardes"]), set(models.CARACTERISTIQUES))

    def test_expose_dans_vers_dict_et_markdown(self):
        p = self._barde()
        self.assertIn("jets", p.vers_dict())
        self.assertEqual(p.vers_dict()["jets"]["competences"]["Tromperie"], 5)
        md = export.en_markdown(p)
        self.assertIn("## Bonus des jets", md)
        self.assertIn("Tromperie : d20 +5", md)


if __name__ == "__main__":
    unittest.main()
