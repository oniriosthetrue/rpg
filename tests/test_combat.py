"""Tests du moteur de combat D&D 5.2.1 (`dnd_perso.combat`).

Lancement :
    python3 -m unittest tests.test_combat -v
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dnd_perso import combat  # noqa: E402


def _pj(cle="pj:hero", pv=10, ca=15, bba=5, des="1d8", mod=2, binit=2):
    return combat.Combattant(
        cle=cle, nom="Hero", camp="pj", pv=pv, pv_max=pv, ca=ca,
        bonus_attaque=bba, des_degats=des, mod_degats=mod, bonus_initiative=binit,
    )


def _mon(cle="mon:0:gob", pv=10, ca=15, bba=4, des="1d6", mod=2, binit=2):
    return combat.Combattant(
        cle=cle, nom="Gobelin", camp="monstre", pv=pv, pv_max=pv, ca=ca,
        bonus_attaque=bba, des_degats=des, mod_degats=mod, bonus_initiative=binit,
    )


class TestInitiative(unittest.TestCase):
    def test_initiative_borne_et_tri(self):
        rng = random.Random(42)
        a = _pj(cle="pj:a", binit=5)
        b = _mon(cle="mon:0:b", binit=0)
        combat.roller_initiative([a, b], rng)
        for c in (a, b):
            self.assertGreaterEqual(c.initiative, 1 + c.bonus_initiative)
            self.assertLessEqual(c.initiative, 20 + c.bonus_initiative)
        # ordre décroissant d'initiative
        ordre = combat.roller_initiative([a, b], rng)
        self.assertGreaterEqual(ordre[0].initiative, ordre[1].initiative)

    def test_reproductible_seed(self):
        def tirage(seed):
            rng = random.Random(seed)
            a = _pj(cle="pj:a", binit=3)
            b = _mon(cle="mon:0:b", binit=1)
            combat.roller_initiative([a, b], rng)
            return a.initiative, b.initiative
        self.assertEqual(tirage(7), tirage(7))


class TestAttaque(unittest.TestCase):
    def test_nat20_critique_double_les_des(self):
        attaquant = _pj(bba=0, des="1d6", mod=3)
        defenseur = _mon(pv=100, ca=30)  # CA imprenable sauf critique
        res = combat.resoudre_attaque(attaquant, defenseur, 20, random.Random(1))
        self.assertTrue(res["critique"])
        self.assertTrue(res["touche"])
        # 2 jets de 1d6 (min 2, max 12) + mod 3 => [5, 15]
        self.assertGreaterEqual(res["degats"], 2 + 3)
        self.assertLessEqual(res["degats"], 12 + 3)

    def test_des_degats_avec_modificateur_statique(self):
        # « 1d6+2 » doit être accepté (monstres du SRD) et borné [3, 8] hors critique.
        attaquant = _pj(bba=20, des="1d6+2", mod=0)
        defenseur = _mon(pv=100, ca=1)
        res = combat.resoudre_attaque(attaquant, defenseur, 15, random.Random(1))
        self.assertTrue(res["touche"])
        self.assertGreaterEqual(res["degats"], 1 + 2)
        self.assertLessEqual(res["degats"], 6 + 2)

    def test_critique_ne_double_pas_le_modificateur(self):
        # « 1d6+2 » en critique = 2×1d6 + 2 (le +2 n'est PAS doublé), + mod_degats.
        attaquant = _pj(bba=0, des="1d6+2", mod=1)
        defenseur = _mon(pv=100, ca=30)
        rng = random.Random(7)
        res = combat.resoudre_attaque(attaquant, defenseur, 20, rng)
        # Rejoue les deux jets pour vérifier la formule exacte.
        r = random.Random(7)
        attendu = r.randint(1, 6) + r.randint(1, 6) + 2 + 1
        self.assertTrue(res["critique"])
        self.assertEqual(res["degats"], attendu)

    def test_nat1_maladresse(self):
        attaquant = _pj(bba=20)  # même +20 échoue sur un nat 1
        defenseur = _mon(ca=1)
        res = combat.resoudre_attaque(attaquant, defenseur, 1, random.Random(1))
        self.assertTrue(res["maladresse"])
        self.assertFalse(res["touche"])
        self.assertEqual(res["degats"], 0)

    def test_seuil_ca(self):
        attaquant = _pj(bba=5)
        defenseur = _mon(ca=15, pv=100)
        # d20=9 => total 14 < 15 => échec
        res = combat.resoudre_attaque(attaquant, defenseur, 9, random.Random(1))
        self.assertFalse(res["touche"])
        # d20=10 => total 15 >= 15 => touché
        res2 = combat.resoudre_attaque(attaquant, defenseur, 10, random.Random(1))
        self.assertTrue(res2["touche"])

    def test_pv_ne_descend_jamais_sous_zero(self):
        attaquant = _pj(bba=20, des="1d100", mod=50)
        defenseur = _mon(pv=3, ca=1)
        res = combat.resoudre_attaque(attaquant, defenseur, 15, random.Random(1))
        self.assertTrue(res["touche"])
        self.assertEqual(defenseur.pv, 0)
        self.assertTrue(res["hors_combat"])


class TestDegatsAuto(unittest.TestCase):
    """Effets qui touchent automatiquement (projectile magique, etc.) : le serveur
    lance les dés, sans jet d'attaque ni CA."""

    def test_projectile_magique_3x1d4_plus_1(self):
        cible = _mon(pv=16, ca=30)  # CA ignorée : auto-touché
        res = combat.resoudre_degats_auto(cible, "1d4", mod=1, nb_fois=3, rng=random.Random(3))
        self.assertTrue(res["ok"])
        self.assertEqual(res["type"], "degats_auto")
        self.assertEqual(len(res["des_lances"]), 3)
        # 3×[1,4] + 1 => [4, 13]
        self.assertGreaterEqual(res["degats"], 3 * 1 + 1)
        self.assertLessEqual(res["degats"], 3 * 4 + 1)
        self.assertEqual(cible.pv, 16 - res["degats"])

    def test_des_avec_modificateur_statique(self):
        # « 1d4+1 » en un seul lancer = 1d4 + 1 (le +1 du dé s'ajoute une fois).
        cible = _mon(pv=16)
        res = combat.resoudre_degats_auto(cible, "1d4+1", rng=random.Random(5))
        self.assertGreaterEqual(res["degats"], 2)
        self.assertLessEqual(res["degats"], 5)

    def test_pv_ne_descend_jamais_sous_zero(self):
        cible = _mon(pv=2)
        res = combat.resoudre_degats_auto(cible, "1d100", mod=50, rng=random.Random(1))
        self.assertEqual(cible.pv, 0)
        self.assertTrue(res["hors_combat"])

    def test_expression_invalide(self):
        cible = _mon(pv=10)
        res = combat.resoudre_degats_auto(cible, "pas_des_des", rng=random.Random(1))
        self.assertFalse(res["ok"])
        self.assertEqual(cible.pv, 10)  # aucune modification

    def test_reproductible_seed(self):
        def tirage(seed):
            return combat.resoudre_degats_auto(
                _mon(pv=50), "1d4", mod=1, nb_fois=3, rng=random.Random(seed)
            )["degats"]
        self.assertEqual(tirage(11), tirage(11))


class TestEtat(unittest.TestCase):
    def test_degats_et_soins_plafonds(self):
        c = _pj(pv=10)
        combat.appliquer_degats(c, 4)
        self.assertEqual(c.pv, 6)
        combat.appliquer_degats(c, 999)
        self.assertEqual(c.pv, 0)
        combat.appliquer_soins(c, 5)
        self.assertEqual(c.pv, 5)
        combat.appliquer_soins(c, 999)
        self.assertEqual(c.pv, 10)  # plafonné à pv_max

    def test_condition_ajout_unique(self):
        c = _pj()
        combat.ajouter_condition(c, "Aveuglé")
        combat.ajouter_condition(c, "Aveuglé")
        self.assertEqual(c.conditions, ["Aveuglé"])


class TestTour(unittest.TestCase):
    def test_tour_suivant_passe_les_morts(self):
        rng = random.Random(3)
        a = _pj(cle="pj:a", binit=10)
        b = _mon(cle="mon:0:b", binit=5)
        c = _mon(cle="mon:1:c", binit=1)
        r = combat.Rencontre.ouvrir("test", [a, b, c], rng=rng)
        # on tue le combattant b (par référence, quel que soit son rang)
        r.combattant(b.cle).pv = 0
        vus = []
        for _ in range(4):
            r.tour_suivant()
            vus.append(r.actif.cle)
        self.assertNotIn(b.cle, vus)  # le mort est sauté

    def test_tour_increment_boucle(self):
        rng = random.Random(5)
        a = _pj(cle="pj:a", binit=10)
        b = _mon(cle="mon:0:b", binit=1)
        r = combat.Rencontre.ouvrir("t", [a, b], rng=rng)
        self.assertEqual(r.tour, 1)
        r.tour_suivant()  # -> b (tour 1)
        r.tour_suivant()  # -> a (tour 2)
        self.assertEqual(r.tour, 2)


class TestFin(unittest.TestCase):
    def test_finie_quand_un_seul_camp_vivant(self):
        rng = random.Random(9)
        a = _pj(cle="pj:a", binit=10)
        b = _mon(cle="mon:0:b", binit=1)
        r = combat.Rencontre.ouvrir("t", [a, b], rng=rng)
        self.assertFalse(r.finie)
        b.pv = 0
        self.assertTrue(r.finie)
        clot = r.cloturer()
        self.assertEqual(clot["vainqueurs"], ["pj"])

    def test_tour_suivant_refuse_si_finie(self):
        rng = random.Random(9)
        a = _pj(cle="pj:a", binit=10)
        b = _mon(cle="mon:0:b", binit=1)
        r = combat.Rencontre.ouvrir("t", [a, b], rng=rng)
        b.pv = 0
        res = r.tour_suivant()
        self.assertFalse(res["ok"])


class TestSerialisation(unittest.TestCase):
    def test_roundtrip(self):
        rng = random.Random(11)
        a = _pj(cle="pj:a", binit=10)
        b = _mon(cle="mon:0:b", binit=1)
        r = combat.Rencontre.ouvrir("t", [a, b], titre="Embuscade", rng=rng)
        d = r.vers_dict()
        r2 = combat.Rencontre.depuis_dict(d)
        self.assertEqual(r2.id, "t")
        self.assertEqual(r2.titre, "Embuscade")
        self.assertEqual([c.cle for c in r2.ordre], [c.cle for c in r.ordre])
        self.assertEqual([c.initiative for c in r2.ordre], [c.initiative for c in r.ordre])


if __name__ == "__main__":
    unittest.main()
