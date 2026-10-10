"""Lancer de dés déterministe (stdlib uniquement).

Fournit :
- ``roll(expr, rng)`` : lance « NdM » ou « NdMkhN » (ex. « 4d6kh3 »),
  en gardant le cas échéant les N meilleurs résultats.
- ``roll_d100(table, rng)`` : tire une ligne d'une table d100
  (liste de couples ``(ligne, valeur)``).

Le générateur ``random.Random`` est injecté pour rendre les tirages
reproductibles via ``--seed``.
"""

from __future__ import annotations

import random
import re

# « NdM », avec modificateur statique optionnel (« 1d6+2 », « 2d8-1 ») et
# option « khN » (« 4d6kh3 »). Le modificateur s'ajoute APRÈS les dés (et
# n'est donc jamais doublé par un coup critique, qui double les dès).
_EXPR_RE = re.compile(
    r"^(\d+)d(\d+)(?:kh(\d+))?(?:([+-])(\d+))?$", re.IGNORECASE
)


def roll(expr: str, rng: random.Random | None = None) -> int:
    """Lance ``NdM`` (ex. « 3d6 »), avec modificateur optionnel (ex. « 1d6+2 »,
    « 2d8-1 ») ou option « khN » (ex. « 4d6kh3 »).

    Retourne la somme des dés (ou des N meilleurs si « khN » est présent),
    additionnée du modificateur statique éventuel. Lève ``ValueError`` si
    l'expression est invalide.
    """
    rng = rng or random.Random()
    m = _EXPR_RE.match(expr.strip())
    if not m:
        raise ValueError(f"Expression de dés invalide : {expr!r}")
    nb, faces, keep, signe, mod = (
        int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5),
    )
    if nb <= 0 or faces <= 0:
        raise ValueError(f"Expression de dés invalide : {expr!r}")
    jets = [rng.randint(1, faces) for _ in range(nb)]
    if keep is not None:
        k = int(keep)
        if k <= 0 or k > nb:
            raise ValueError(f"Nombre de dés à conserver invalide dans {expr!r}")
        jets = sorted(jets, reverse=True)[:k]
    total = sum(jets)
    if mod is not None:
        total += int(mod) if signe == "+" else -int(mod)
    return total


def decomposer(expr: str) -> tuple[str, int]:
    """Sépare une expression « NdM±K » en (dès « NdM », modificateur signé).

    Ex. « 1d6+2 » -> (« 1d6 », 2) ; « 2d8-1 » -> (« 2d8 », -1) ;
    « 4d6kh3 » -> (« 4d6kh3 », 0). Sert à doubler UNIQUEMENT les dés lors d'un
    coup critique (le modificateur statique n'est jamais doublé). Lève
    ``ValueError`` si l'expression est invalide.
    """
    m = _EXPR_RE.match(expr.strip())
    if not m:
        raise ValueError(f"Expression de dés invalide : {expr!r}")
    nb, faces, keep, signe, mod = (
        int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5),
    )
    if nb <= 0 or faces <= 0:
        raise ValueError(f"Expression de dés invalide : {expr!r}")
    des = f"{nb}d{faces}" + (f"kh{keep}" if keep is not None else "")
    stat = 0
    if mod is not None:
        stat = int(mod) if signe == "+" else -int(mod)
    return des, stat


def roll_d100(table: list[tuple[int, str]], rng: random.Random | None = None) -> tuple[int, str]:
    """Tire une ligne d'une table d100 (liste de ``(ligne, valeur)``).

    Un résultat de 0 (tirage « 00 » sur deux d10) est traité comme 100.
    Lève ``ValueError`` si la table est vide.
    """
    rng = rng or random.Random()
    if not table:
        raise ValueError("Table d100 vide.")
    tirage = rng.randint(1, 100)
    # Recherche de la ligne dont la borne supérieure couvre le tirage.
    for ligne, valeur in table:
        borne = 100 if ligne == 0 else ligne
        if tirage <= borne:
            return (ligne if ligne != 0 else 100, valeur)
    # Filet de sécurité : dernière ligne de la table.
    return table[-1]
