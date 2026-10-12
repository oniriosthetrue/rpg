"""Test de fumée de la garde « zone sûre / zone dangereuse » (router combat).

Rejoue le bug observé en jeu : le MJ fait « apparaître » 10 bandits au Carrefour
du Sel (lieu sans rencontre = zone sûre) -> le serveur doit REFUSER. Puis ouvre
les 2 gardes réellement planifiés à la Tour du Griffon Noir (zone dangereuse) ->
le serveur doit ACCEPTER.

Appelle directement la fonction `ouvrir` du router (pas via `main`, qui dépend
de pydantic_ai indisponible hors conteneur).

Dossiers TEMPORAIRES : ne touche jamais data-perso/ ni data-combat/ réels.
Lancement : PYTHONPATH=packages:apps/api python3 tests/smoke_zone_garde.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "packages"))
sys.path.insert(0, str(RACINE / "apps" / "api"))

tmp = Path(tempfile.mkdtemp(prefix="zone-garde-"))
perso = tmp / "perso"
campagne = tmp / "campagne"
combat = tmp / "combat"
perso.mkdir()
campagne.mkdir()

# Copie la vraie fiche Conan + la vraie campagne (id 2026-10-12-173528).
shutil.copy(RACINE / "data-perso" / "Conan.json", perso / "Conan.json")
shutil.copy(RACINE / "data-campagne" / "campagne-2026-10-12-173528.json",
            campagne / "campagne-2026-10-12-173528.json")

os.environ["DND_PERSO_DIR"] = str(perso)
os.environ["DND_COMBAT_DIR"] = str(combat)
os.environ["DND_CAMPAGNE_DIR"] = str(campagne)
os.environ["DND_API_KEY"] = "test-key"

from jdr_api.routers import combat as r_combat  # noqa: E402

CID = "2026-10-12-173528"
H = "test-key"

ok = ko = 0


def check(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print(f"  \u2713 {nom}")
    else:
        ko += 1
        print(f"  \u2717 {nom}  {detail}")


def bandits(n):
    return [{"type": "pj", "nom": "Conan"}] + [
        {"type": "monstre", "nom": "Bandit", "pv": 11, "ca": 10, "attaque": 4,
         "degats": "1d6+2", "mod_degats": 2, "init_bonus": 1}
        for _ in range(n)
    ]


def est_refus(r):
    return r.get("type") == "erreur" or r.get("ok") is False


print("Garde zone sûre / zone dangereuse")

# 1) 10 bandits au Carrefour du Sel (zone SÛRE) -> refus.
r = r_combat.ouvrir({"titre": "Embuscade", "lieu": "Le Carrefour du Sel",
                     "campagne_id": CID, "combattants": bandits(10)}, H)
check("10 bandits au Carrefour (zone sûre) = REFUSÉ", est_refus(r),
      json.dumps(r, ensure_ascii=False)[:220])

# 2) 10 bandits SANS lieu (aucune zone n'autorise 10 bandits) -> refus.
r = r_combat.ouvrir({"titre": "Embuscade", "campagne_id": CID,
                     "combattants": bandits(10)}, H)
check("10 bandits sans lieu (surnombre vs plan) = REFUSÉ", est_refus(r),
      json.dumps(r, ensure_ascii=False)[:220])

# 3) 2 Bandits à la Tour du Griffon Noir (zone DANGEREUSE, plan = 2) -> accepté.
r = r_combat.ouvrir({"titre": "La Tour du Griffon Noir",
                     "lieu": "La Tour du Griffon Noir", "campagne_id": CID,
                     "combattants": bandits(2)}, H)
check("2 Bandits à la Tour (zone dangereuse) = ACCEPTÉ", not est_refus(r),
      json.dumps(r, ensure_ascii=False)[:220])

# 4) Monstre jamais planifié (Ours-garou) dans une zone dangereuse -> refus.
r = r_combat.ouvrir({"titre": "Ours", "lieu": "La Tour du Griffon Noir",
                     "campagne_id": CID,
                     "combattants": [{"type": "pj", "nom": "Conan"},
                                     {"type": "monstre", "nom": "Ours-garou", "pv": 59,
                                      "ca": 12, "attaque": 7, "degats": "2d6+4",
                                      "mod_degats": 4, "init_bonus": 2}]}, H)
check("Ours-garou non planifié = REFUSÉ", est_refus(r),
      json.dumps(r, ensure_ascii=False)[:220])

# 5) Les loups du col (zone dangereuse, plan = 2 Loups) -> accepté.
r = r_combat.ouvrir({"id": "t-loups", "titre": "Les loups du col",
                     "lieu": "Le Sentier de la Veuve", "campagne_id": CID,
                     "combattants": [{"type": "pj", "nom": "Conan"}] + [
                         {"type": "monstre", "nom": "Loup", "pv": 11, "ca": 12,
                          "attaque": 4, "degats": "2d4+2", "mod_degats": 2,
                          "init_bonus": 2} for _ in range(2)]}, H)
check("2 Loups au Sentier (zone dangereuse) = ACCEPTÉ", not est_refus(r),
      json.dumps(r, ensure_ascii=False)[:220])

# 6) Combat hors campagne (pas de campagne_id) -> toujours autorisé (non bloqué).
r = r_combat.ouvrir({"id": "t-hors", "titre": "Hors campagne",
                     "combattants": bandits(3)}, H)
check("Combat sans campagne = ACCEPTÉ (non bloqué)", not est_refus(r),
      json.dumps(r, ensure_ascii=False)[:220])

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{ok} OK / {ko} KO")
sys.exit(1 if ko else 0)
