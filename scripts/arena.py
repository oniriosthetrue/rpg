#!/usr/bin/env python3
"""Arène de test du moteur de combat (phase C2b) — headless, déterministe.

Fait s'affronter un **PJ** (fiche JSON de `data-perso/`) contre un **monstre**
(fiche RAG de `dnd/srd-5.2.1/04-monstres/`) sur N rencontres, et agrège les
résultats pour juger l'**équilibrage** et valider l'**arithmétique** du moteur
sans passer par le LLM ni la stack.

N'importe **que** `dnd_perso` (aucun FastAPI/HTTP) : tourne hors conteneur.

Usage :
    python3 scripts/arena.py --pj onirios --monstre combattant-gobelin \
        --nb 1000 --seed 42

Le `--seed` rend la série **reproductible** (non-régression : deux runs à même
seed donnent des chiffres identiques).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dnd_perso import combat, extract  # noqa: E402
from dnd_perso import models  # noqa: E402

MONSTRES_DIR = extract.CORPUS / "04-monstres"

# --- Regex de lecture d'une fiche monstre (SRD 5.2.1, français) -------------
_RE_CA = re.compile(r"CA\s*:\*\*\s*(\d+)")
_RE_INIT = re.compile(r"Initiative\s*:\*\*\s*([+-]?\d+)")
_RE_PV = re.compile(r"Pv\s*:\*\*\s*(\d+)")
_RE_BM = re.compile(r"BM\s*\+?(\d+)")
# « Cimeterre. Corps à corps : +4, ... Touché : 5 (1d6 + 2) dégâts ... »
_RE_ATK_BONUS = re.compile(r":\s*([+-]?\d+)\s*,")
_RE_DEGATS = re.compile(r"Touch[ée]\s*:.*?\(\s*(\d+d\d+)(?:\s*([+-])\s*(\d+))?")


def _lire_fiche_monstre(nom: str) -> combat.Combattant:
    """Construit un Combattant « monstre » depuis sa fiche RAG."""
    chemin = MONSTRES_DIR / f"{nom}.md"
    if not chemin.exists():
        raise SystemExit(f"Fiche monstre introuvable : {chemin}")
    _keys, corps = extract._parse_fiche(chemin.read_text(encoding="utf-8"))

    def _cherche(rx: re.Pattern, defaut=None):
        m = rx.search(corps)
        return m.group(1) if m else defaut

    ca = int(_cherche(_RE_CA, "10"))
    binit = int(_cherche(_RE_INIT, "0"))
    pv = int(_cherche(_RE_PV, "10"))
    bm = int(_cherche(_RE_BM, "2"))

    # Première action offensive : bonus d'attaque + dés/mod de dégâts.
    bba = 0
    des, mod = "1d6", 0
    for ligne in corps.splitlines():
        if "Touch" in ligne and "(" in ligne:
            mb = _RE_ATK_BONUS.search(ligne)
            if mb:
                bba = int(mb.group(1))
            md = _RE_DEGATS.search(ligne)
            if md:
                des = md.group(1)
                if md.group(2) and md.group(3):
                    mod = int(md.group(2) + md.group(3))
            break

    cle = f"mon:0:{nom}"
    return combat.Combattant(
        cle=cle, nom=nom, camp="monstre", pv=pv, pv_max=pv, ca=ca,
        bonus_attaque=bba, des_degats=des, mod_degats=mod, bonus_initiative=binit,
    )


def _lire_pj(nom: str) -> combat.Combattant:
    """Construit un Combattant « PJ » depuis sa fiche JSON (data-perso/).

    La fiche PJ ne stocke pas le bonus d'attaque ni l'arme : on les **dérive**
    (Force + bonus de maîtrise, 1d8) — approximation assumée pour l'équilibrage,
    surchargeable via `--bba/--des/--mod`.
    """
    chemin = extract.PERSO_DIR / f"{nom}.json"
    if not chemin.exists():
        raise SystemExit(f"Fiche PJ introuvable : {chemin}")
    p = models.Personnage.depuis_dict(json.loads(chemin.read_text(encoding="utf-8")))
    pv = p.pv
    return combat.Combattant(
        cle=f"pj:{nom}", nom=p.nom, camp="pj", pv=pv, pv_max=pv, ca=p.ca,
        bonus_attaque=p.carac.mod_for() + p.bonus_maitrise,
        des_degats="1d8", mod_degats=p.carac.mod_for(),
        bonus_initiative=p.initiative,
    )


def _simuler(pj: combat.Combattant, mon: combat.Combattant, rng: random.Random) -> dict:
    """Un combat complet. Retourne : vainqueur, tours, critiques PJ, PV PJ restants."""
    r = combat.Rencontre.ouvrir("arene", [
        combat.Combattant.depuis_dict(pj.vers_dict()),
        combat.Combattant.depuis_dict(mon.vers_dict()),
    ], rng=rng)

    critiques = 0
    for _ in range(combat.PLAFOND_TOURS):
        if r.finie:
            break
        a = r.actif
        cible = next((c for c in r.ordre if c.camp != a.camp and c.vivant), None)
        if cible is None:
            break
        res = combat.roller_attaque(a, cible, rng)
        if res["critique"] and a.camp == "pj":
            critiques += 1
        r.tour_suivant()

    camps = r.camps_en_jeu
    vainqueur = "pj" if camps == {"pj"} else ("monstre" if camps == {"monstre"} else "nul")
    pj_final = r.combattant(pj.cle).pv
    return {
        "vainqueur": vainqueur,
        "tours": r.tour,
        "critiques_pj": critiques,
        "pv_pj_restants": pj_final,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Arène de test du moteur de combat.")
    ap.add_argument("--pj", required=True, help="Nom du PJ (fiche data-perso/).")
    ap.add_argument("--monstre", required=True, help="Nom du monstre (fiche 04-monstres/).")
    ap.add_argument("--nb", type=int, default=1000, help="Nombre de rencontres (défaut 1000).")
    ap.add_argument("--seed", type=int, default=None, help="Graine (reproductibilité).")
    ap.add_argument("--bba", type=int, default=None, help="Surcharger le bonus d'attaque du PJ.")
    ap.add_argument("--des", default=None, help="Surcharger les dés de dégâts du PJ (ex. 1d8).")
    ap.add_argument("--mod", type=int, default=None, help="Surcharger le modificateur de dégâts du PJ.")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    pj = _lire_pj(args.pj)
    if args.bba is not None:
        pj.bonus_attaque = args.bba
    if args.des is not None:
        pj.des_degats = args.des
    if args.mod is not None:
        pj.mod_degats = args.mod
    mon = _lire_fiche_monstre(args.monstre)

    print(f"Arène : {pj.nom} (PV {pj.pv_max}, CA {pj.ca}, +{pj.bonus_attaque}, "
          f"{pj.des_degats}{pj.mod_degats:+d}, init {pj.bonus_initiative:+d})")
    print(f"  vs  {mon.nom} (PV {mon.pv_max}, CA {mon.ca}, +{mon.bonus_attaque}, "
          f"{mon.des_degats}{mon.mod_degats:+d}, init {mon.bonus_initiative:+d})")
    print(f"{args.nb} rencontres" + (f" (seed {args.seed})" if args.seed is not None else "") + "\n")

    resultats = [_simuler(pj, mon, rng) for _ in range(args.nb)]

    victoires = sum(1 for r in resultats if r["vainqueur"] == "pj")
    defaites = sum(1 for r in resultats if r["vainqueur"] == "monstre")
    nuls = sum(1 for r in resultats if r["vainqueur"] == "nul")
    tours = [r["tours"] for r in resultats]
    critiques = sum(r["critiques_pj"] for r in resultats)
    pv_restants = [r["pv_pj_restants"] for r in resultats if r["vainqueur"] == "pj"]

    print(f"Victoires PJ   : {victoires:5d}  ({victoires / args.nb:6.1%})")
    print(f"Défaites PJ    : {defaites:5d}  ({defaites / args.nb:6.1%})")
    print(f"Nuls/plafond   : {nuls:5d}  ({nuls / args.nb:6.1%})")
    print(f"Tours          : moy {mean(tours):.1f} | min {min(tours)} | max {max(tours)}")
    print(f"Critiques PJ   : {critiques} ({critiques / args.nb:.2f}/combat)")
    if pv_restants:
        print(f"PV PJ restants (victoires) : moy {mean(pv_restants):.1f}")

    # Diagnostic d'équilibrage (seuils indicatifs).
    taux = victoires / args.nb
    if taux >= 0.95:
        bilan = "⚠️ PJ trop fort (quasi-systématique) — monstre sous-dimensionné."
    elif taux <= 0.05:
        bilan = "⚠️ PJ trop faible (quasi-jamais) — monstre surdimensionné."
    elif 0.4 <= taux <= 0.7:
        bilan = "✅ Équilibrage plausible pour un affrontement tendu."
    else:
        bilan = "ℹ️ Équilibrage dans une fourchette acceptable, à affiner au goût."
    print("\n" + bilan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
