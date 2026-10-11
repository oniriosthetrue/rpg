"""Tests du moteur de campagne (dnd_perso.campagne) — pur, sans HTTP.

Lancement :
    python3 -m unittest tests.test_campagne -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dnd_perso import campagne as cp  # noqa: E402


def _campagne_valide() -> cp.Campagne:
    return cp.Campagne(
        id="scen-test",
        titre="Le Secret du Moulin",
        pj=["Aldric", "Brune"],
        phase="accroche",
        danger="normale",
        accroche="Le meunier a disparu cette nuit.",
        enjeux="Retrouver le meunier avant l'aube.",
        motivations="Le moulin appartient à la famille d'Aldric.",
        pnj=[
            cp.PNJ("Mireille", objectif="Protéger le secret", faille="Peur du feu", attitude="méfiante"),
            cp.PNJ("Le Meunier", objectif="Survivre", faille="Blesse à la jambe", attitude="allié"),
        ],
        defis=[cp.Defi("Franchir la porte", approches=["Crochetage", "Force", "Négociation"])],
        crochets=[
            cp.Crochet("c1", "L'héritage d'Aldric", lie_a_pj="Aldric"),
            cp.Crochet("c2", "La dette de Brune", lie_a_pj="Brune"),
        ],
        blocs=[cp.Bloc("b1", "Embuscade au pont")],
    )


class TestValidation(unittest.TestCase):
    def test_campagne_valide(self):
        self.assertEqual(_campagne_valide().valider_structure(), [])

    def test_moins_de_2_crochets(self):
        c = _campagne_valide()
        c.crochets = [cp.Crochet("c1", "X", lie_a_pj="Aldric")]
        problemes = c.valider_structure()
        self.assertTrue(any("2 crochets" in p for p in problemes))

    def test_defi_une_seule_approche(self):
        c = _campagne_valide()
        c.defis = [cp.Defi("Porte", approches=["Force"])]
        problemes = c.valider_structure()
        self.assertTrue(any("2 approches" in p for p in problemes))

    def test_pnj_incomplet(self):
        c = _campagne_valide()
        c.pnj.append(cp.PNJ("Inconnu", objectif="?", faille="", attitude=""))
        problemes = c.valider_structure()
        self.assertTrue(any("Inconnu" in p for p in problemes))

    def test_phase_inconnue(self):
        c = _campagne_valide()
        c.phase = "nimporte_quoi"
        self.assertTrue(any("Phase inconnue" in p for p in c.valider_structure()))


class TestTransitions(unittest.TestCase):
    def test_avancer_phase(self):
        c = _campagne_valide()
        self.assertEqual(c.avancer_phase()["phase"], "montee")
        c.avancer_phase()
        self.assertEqual(c.phase, "climax")
        c.avancer_phase()
        self.assertEqual(c.phase, "conclusion")
        r = c.avancer_phase()
        self.assertFalse(r["ok"])

    def test_resoudre_crochet(self):
        c = _campagne_valide()
        r = c.modifier("resoudre_crochet", id="c1")
        self.assertTrue(r["ok"])
        self.assertEqual(c.crochet_par_id("c1").statut, "resolvee")

    def test_crochet_inconnu(self):
        c = _campagne_valide()
        self.assertFalse(c.modifier("resoudre_crochet", id="zz")["ok"])

    def test_action_inconnue(self):
        c = _campagne_valide()
        self.assertFalse(c.modifier("invente")["ok"])

    def test_deplacer_bloc(self):
        c = _campagne_valide()
        r = c.modifier("deplacer_bloc", id="b1", position="reserve")
        self.assertTrue(r["ok"])
        b = c.bloc_par_id("b1")
        self.assertTrue(b.deplace)
        self.assertEqual(b.position, "reserve")

    def test_rencontrer_pnj_et_attitude(self):
        c = _campagne_valide()
        c.modifier("rencontrer_pnj", nom="Mireille")
        self.assertTrue(c.pnj_par_nom("Mireille").rencontre)
        c.modifier("changer_attitude", nom="Mireille", attitude="alliée")
        self.assertEqual(c.pnj_par_nom("Mireille").attitude, "alliée")

    def test_indice_recompense_lieu(self):
        c = _campagne_valide()
        c.lieux = [cp.Lieu("Moulin")]
        c.modifier("ajouter_indice", indice="Une empreinte de patte")
        c.modifier("accorder_recompense", recompense="10 po")
        c.modifier("decouvrir_lieu", nom="Moulin")
        self.assertEqual(c.indices, ["Une empreinte de patte"])
        self.assertEqual(c.recompenses, ["10 po"])
        self.assertTrue(c.lieu_par_nom("Moulin").decouvert)

    def test_cloturer(self):
        c = _campagne_valide()
        c.cloturer()
        self.assertFalse(c.active)

    def test_rejouer_reinitialise_sans_toucher_la_trame(self):
        c = _campagne_valide()
        c.lieux = [cp.Lieu("Moulin", description="Une roue bloquée.")]
        # On joue la campagne : phase avancée, crochet résolu, lieu découvert,
        # PNJ rencontré, bloc déplacé, indice + chronologie accumulés, clôturée.
        c.avancer_phase()
        c.avancer_phase()
        c.modifier("resoudre_crochet", id="c1")
        c.modifier("decouvrir_lieu", nom="Moulin")
        c.modifier("rencontrer_pnj", nom="Mireille")
        c.modifier("deplacer_bloc", id="b1", position="reserve")
        c.modifier("ajouter_indice", indice="Une empreinte")
        c.cloturer()
        # On rejoue : la trame survit, l'état de partie repart de zéro.
        titre, accroche = c.titre, c.accroche
        synopsis = c.synopsis
        r = c.rejouer()
        self.assertTrue(r["ok"])
        self.assertEqual(c.phase, "accroche")
        self.assertTrue(c.active)
        self.assertEqual(c.indices, [])
        self.assertEqual(c.recompenses, [])
        self.assertEqual(c.crochet_par_id("c1").statut, "ouverte")
        self.assertFalse(c.lieu_par_nom("Moulin").decouvert)
        self.assertFalse(c.pnj_par_nom("Mireille").rencontre)
        self.assertFalse(c.bloc_par_id("b1").deplace)
        self.assertEqual(c.bloc_par_id("b1").position, "actif")
        # Trame + PJ conservés intacts.
        self.assertEqual(c.titre, titre)
        self.assertEqual(c.accroche, accroche)
        self.assertEqual(c.synopsis, synopsis)
        self.assertEqual(c.pj, ["Aldric", "Brune"])
        self.assertEqual(len(c.crochets), 2)
        self.assertEqual(c.lieux[0].description, "Une roue bloquée.")


class TestEcrireStructure(unittest.TestCase):
    """`ecrire_structure` persiste la trame conçue par le MJ sans écraser le cadrage
    ni l'état de partie (l'outil qui manquait : sinon la campagne reste vide)."""

    def _coquille(self) -> cp.Campagne:
        # Campagne ouverte par le wizard : cadrage seul, trame vide.
        return cp.Campagne(
            id="scen-vide", titre="", pj=["Elminster"], mode="surprise",
            age_joueur=45, duree="one-shot", piliers=["combat", "exploration"],
            ton="sombre", niveaux=[1],
        )

    def test_ecrit_la_trame_et_valide(self):
        c = self._coquille()
        self.assertTrue(c.valider_structure())  # vide -> avertissements
        etat = c.ecrire_structure({
            "titre": "Les Marges du Grimoire",
            "synopsis": "Un grimoire dévore les scribes.",
            "accroche": "La lettre d'Aldren est griffée d'un suc.",
            "enjeux": "Retrouver Aldren.",
            "pnj": [{"nom": "Aldren", "objectif": "Survivre", "faille": "Lié au grimoire", "attitude": "allié"}],
            "crochets": [
                {"id": "c1", "titre": "La dette envers Aldren", "lie_a_pj": "Elminster"},
                {"id": "c2", "titre": "Le savoir dangereux", "lie_a_pj": "Elminster"},
            ],
            "defis": [{"nom": "Entrer", "approches": ["Forcer", "Discrétion"]}],
        })
        self.assertEqual(c.titre, "Les Marges du Grimoire")
        self.assertEqual(len(c.pnj), 1)
        self.assertTrue(c.pnj[0].complet())
        self.assertEqual(len([x for x in c.crochets if x.lie_a_pj]), 2)
        self.assertTrue(etat["structure_valide"])
        self.assertEqual(etat["avertissements_structure"], [])

    def test_preserve_le_cadrage(self):
        c = self._coquille()
        c.ecrire_structure({"titre": "X", "accroche": "Y"})
        # Cadrage intact.
        self.assertEqual(c.mode, "surprise")
        self.assertEqual(c.age_joueur, 45)
        self.assertEqual(c.duree, "one-shot")
        self.assertEqual(c.piliers, ["combat", "exploration"])
        self.assertEqual(c.ton, "sombre")
        self.assertEqual(c.pj, ["Elminster"])
        self.assertEqual(c.niveaux, [1])

    def test_preserve_l_etat_de_partie(self):
        c = self._coquille()
        c.ecrire_structure({
            "crochets": [{"id": "c1", "titre": "A", "lie_a_pj": "Elminster"}],
            "pnj": [{"nom": "P", "objectif": "o", "faille": "f", "attitude": "a"}],
        })
        c.modifier("resoudre_crochet", id="c1")
        c.modifier("ajouter_indice", indice="poussière")
        c.avancer_phase()
        # Réécriture partielle de la trame : ne doit PAS effacer phase/indices/statut.
        c.ecrire_structure({"synopsis": "nouveau"})
        self.assertEqual(c.phase, "montee")
        self.assertEqual(c.indices, ["poussière"])
        self.assertEqual(c.crochet_par_id("c1").statut, "resolvee")
        self.assertEqual(c.synopsis, "nouveau")

    def test_ne_ecrase_que_les_champs_fournis(self):
        c = self._coquille()
        c.ecrire_structure({"titre": "Premier", "synopsis": "S1"})
        c.ecrire_structure({"titre": "Second"})
        self.assertEqual(c.titre, "Second")
        self.assertEqual(c.synopsis, "S1")  # non fourni -> préservé

    def test_danger_invalide_ignore(self):
        c = self._coquille()
        c.ecrire_structure({"danger": "apocalyptique"})
        self.assertEqual(c.danger, "normale")  # inchangé


class TestSerialisation(unittest.TestCase):
    def test_roundtrip(self):
        c = _campagne_valide()
        c.modifier("resoudre_crochet", id="c1")
        c.modifier("ajouter_indice", indice="poussière")
        d = c.vers_dict()
        c2 = cp.Campagne.depuis_dict(d)
        self.assertEqual(c2.vers_dict(), d)
        self.assertEqual(c2.crochet_par_id("c1").statut, "resolvee")
        self.assertEqual(c2.indices, ["poussière"])

    def test_etat(self):
        etat = _campagne_valide().etat()
        self.assertTrue(etat["ok"])
        self.assertTrue(etat["structure_valide"])
        self.assertEqual(etat["type"], "campagne")


class TestAdvisory(unittest.TestCase):
    def test_tres_facile(self):
        r = cp.advisory_difficulte([5, 5], [cp.MonstreScenarise("Rat", nb=1, cr="1/8")])
        self.assertEqual(r["degre"], "tres_facile")

    def test_mortelle(self):
        r = cp.advisory_difficulte([1], [cp.MonstreScenarise("Dragon", nb=1, cr="13")])
        self.assertEqual(r["degre"], "mortelle")

    def test_effectif_compte(self):
        # 10 loups CR1 = 4000 XP vs groupe de 2 niv.3 (mortelle=1200) -> mortelle.
        r = cp.advisory_difficulte([3, 3], [cp.MonstreScenarise("Loup", nb=10, cr="1")])
        self.assertEqual(r["degre"], "mortelle")
        self.assertEqual(r["xp_monstres"], 4000)

    def test_cr_inconnu_signale(self):
        r = cp.advisory_difficulte([5], [cp.MonstreScenarise("Mystère", cr="999")])
        self.assertIn("Mystère", r["cr_inconnus"])

    def test_sans_niveau(self):
        r = cp.advisory_difficulte([], [cp.MonstreScenarise("Rat", cr="0")])
        self.assertFalse(r["ok"])


class TestFrontMatter(unittest.TestCase):
    MD = """---
id: scen-mineur
titre: Test Mineur
pj: [Aldric, Brune]
danger: normale
pnj:
  - nom: Mireille
    objectif: Protéger
    faille: Peur
    attitude: méfiante
  - nom: Gaspard
    objectif: Vendre
    faille: Cupide
    attitude: neutre
crochets:
  - id: c1
    titre: Héritage
    lie_a_pj: Aldric
  - id: c2
    titre: Dette
    lie_a_pj: Brune
defis:
  - nom: La porte
    approches: [Force, Dialogue]
---

## Accroche
Le meunier a disparu.
"""

    def test_parse_front_matter(self):
        entete, corps = cp.parser_front_matter(self.MD)
        self.assertEqual(entete["id"], "scen-mineur")
        self.assertEqual(entete["pj"], ["Aldric", "Brune"])
        self.assertEqual(len(entete["pnj"]), 2)
        self.assertEqual(entete["pnj"][0]["nom"], "Mireille")
        self.assertIn("meunier", corps)

    def test_campagne_depuis_markdown(self):
        c = cp.campagne_depuis_markdown(self.MD)
        self.assertEqual(c.id, "scen-mineur")
        self.assertEqual(len(c.pnj), 2)
        self.assertEqual(len(c.crochets), 2)
        self.assertEqual(c.defis[0].approches, ["Force", "Dialogue"])
        self.assertEqual(c.valider_structure(), [])

    def test_liste_en_ligne(self):
        entete, _ = cp.parser_front_matter("---\ntags: [a, b, c]\n---\ncorps")
        self.assertEqual(entete["tags"], ["a", "b", "c"])


class TestFixtureScenario(unittest.TestCase):
    """Le scénario d'exemple du dépôt (dnd/scenarios/test-mineur.md) doit être
    un brief valide qui exerce les 5 principes et passe valider_structure()."""

    CHEMIN = Path(__file__).resolve().parent.parent / "dnd" / "scenarios" / "test-mineur.md"

    def test_fixture_sur_disque_valide(self):
        self.assertTrue(self.CHEMIN.exists(), "scénario d'exemple absent")
        c = cp.campagne_depuis_markdown(self.CHEMIN.read_text(encoding="utf-8"))
        self.assertEqual(c.valider_structure(), [])
        # Principe 1 : >=2 crochets liés au background d'un PJ.
        self.assertGreaterEqual(len([x for x in c.crochets if x.lie_a_pj]), 2)
        # Principe 2 : >=2 approches par défi.
        self.assertTrue(all(len(d.approches) >= 2 for d in c.defis))
        # Principe 3 : les 3 piliers couverts par les lieux.
        piliers = {p for l in c.lieux for p in l.piliers}
        self.assertLessEqual({"exploration", "social", "combat"}, piliers)
        # PNJ complets (objectif + faille + attitude).
        self.assertTrue(all(p.complet() for p in c.pnj))
        # Round-trip dict fidèle.
        self.assertEqual(cp.Campagne.depuis_dict(c.vers_dict()).vers_dict(), c.vers_dict())


if __name__ == "__main__":
    unittest.main()
