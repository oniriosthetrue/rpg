"""Test de fumée du router combat (C3) — hors stack, via TestClient.

Utilise des dossiers TEMPORAIRES (perso + combat) pour ne jamais toucher
data-perso/ ni créer data-combat/ réels. Vérifie le cycle complet :
ouvrir -> etat -> jet-monstre -> jet-joueur -> tour-suivant -> patch -> cloturer,
et la répercussion des PV PJ sur la fiche.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

tmp = tempfile.mkdtemp(prefix="combat-smoke-")
perso = Path(tmp) / "perso"
perso.mkdir()
# Copie la vraie fiche pour que la répercussion PV écrive la COPIE, pas l'originale.
shutil.copy(RACINE / "data-perso" / "onirios.json", perso / "onirios.json")

os.environ["DND_PERSO_DIR"] = str(perso)
os.environ["DND_COMBAT_DIR"] = str(Path(tmp) / "combat")
os.environ["DND_API_KEY"] = "test-key"

from fastapi.testclient import TestClient  # noqa: E402
from jdr_api.main import app  # noqa: E402

client = TestClient(app)
H = {"X-API-Key": "test-key"}
ok = 0
ko = 0


def check(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print(f"  \u2713 {nom}")
    else:
        ko += 1
        print(f"  \u2717 {nom}  {detail}")


# --- Auth refusée ---
r = client.get("/api/combat/x")
check("auth sans clé -> erreur", r.status_code == 200 and r.json()["ok"] is False)

# --- Ouvrir une rencontre ---
corps = {
    "id": "test-1",
    "titre": "Embuscade",
    "combattants": [
        {"type": "pj", "nom": "onirios"},
        {"type": "monstre", "nom": "gobelin", "pv": 7, "ca": 15, "attaque": 4,
         "degats": "1d6+2", "init_bonus": 2, "nb": 2},
    ],
}
r = client.post("/api/combat/ouvrir", json=corps, headers=H)
j = r.json()
check("ouvrir -> ok", j.get("ok") is True, str(j)[:200])
check("ouvrir -> 3 combattants", len(j.get("ordre", [])) == 3, str(j.get("ordre")))
check("ouvrir -> v:1", j.get("v") == 1)
check("ouvrir -> cle pj", any(c["cle"] == "pj:onirios" for c in j.get("ordre", [])))
check("ouvrir -> 2 gobelins", sum(1 for c in j.get("ordre", []) if c["nom"].startswith("gobelin")) == 2)
check("ouvrir -> ordre trié desc", [c["initiative"] for c in j.get("ordre", [])] == sorted([c["initiative"] for c in j.get("ordre", [])], reverse=True))

# --- Doublon refusé ---
r = client.post("/api/combat/ouvrir", json=corps, headers=H)
check("ouvrir doublon -> erreur", r.json()["ok"] is False)

# --- Etat ---
r = client.get("/api/combat/test-1", headers=H)
check("etat -> ok", r.json().get("ok") is True)
check("etat -> actif présent", "actif" in r.json())

# NB : le jet-monstre (aléatoire, peut tuer le PJ à 6 PV et clore la rencontre
# de façon légitime) est testé dans une rencontre dédiée « test-2 » plus bas,
# pour ne pas casser les vérifications structurelles déterministes de test-1.

# --- jet-monstre refusé si attaquant = PJ ---
gob = next(c["cle"] for c in j["ordre"] if c["nom"].startswith("gobelin"))
r = client.post("/api/combat/test-1/jet-monstre", json={"attaquant": "pj:onirios", "cible": gob}, headers=H)
check("jet-monstre PJ -> refus", r.json()["ok"] is False)

# --- jet-joueur (pj -> monstre), le joueur annonce son d20 ---
r = client.post("/api/combat/test-1/jet-joueur", json={"attaquant": "pj:onirios", "cible": gob, "de_attaque": 20}, headers=H)
jj = r.json()
check("jet-joueur -> ok", jj.get("ok") is True, str(jj)[:200])
check("jet-joueur -> critique nat20", jj.get("critique") is True)
check("jet-joueur -> touche", jj.get("touche") is True)

# d20 hors bornes
r = client.post("/api/combat/test-1/jet-joueur", json={"attaquant": "pj:onirios", "cible": gob, "de_attaque": 25}, headers=H)
check("jet-joueur d20 invalide -> erreur", r.json()["ok"] is False)

# --- tour-suivant ---
r = client.post("/api/combat/test-1/tour-suivant", headers=H)
check("tour-suivant -> ok", r.json().get("ok") is True)

# --- patch degats sur un monstre ---
r = client.patch("/api/combat/test-1", json={"cle": gob, "action": "degats", "valeur": 3}, headers=H)
check("patch degats monstre -> ok", r.json().get("ok") is True, str(r.json())[:150])

# --- patch condition ---
r = client.patch("/api/combat/test-1", json={"cle": gob, "action": "condition", "valeur": "aveuglé"}, headers=H)
check("patch condition -> ok", r.json().get("ok") is True)

# --- patch degats sur le PJ -> répercussion déterministe sur la fiche ---
fiche_avant = json.loads((perso / "onirios.json").read_text(encoding="utf-8")).get("pv_actuels", -1)
r = client.patch("/api/combat/test-1", json={"cle": "pj:onirios", "action": "degats", "valeur": 2}, headers=H)
check("patch degats PJ -> ok", r.json().get("ok") is True)
fiche_apres = json.loads((perso / "onirios.json").read_text(encoding="utf-8")).get("pv_actuels", -1)
check("patch degats PJ -> répercuté sur fiche", fiche_apres >= 0 and fiche_apres < 6, f"pv_actuels={fiche_apres}")

# --- patch action inconnue ---
r = client.patch("/api/combat/test-1", json={"cle": gob, "action": "téléport", "valeur": 1}, headers=H)
check("patch action inconnue -> erreur", r.json()["ok"] is False)

# --- jet-monstre aléatoire dans une rencontre dédiée (test-2) ---
# Un gobelin qui touche peut mettre le PJ à 0 PV et clore la rencontre : c'est
# un comportement légitime du moteur. On vérifie la cohérence dans tous les cas.
corps2 = {
    "id": "test-2",
    "titre": "Embuscade 2",
    "combattants": [
        {"type": "pj", "nom": "onirios"},
        {"type": "monstre", "nom": "orque", "pv": 30, "ca": 12, "attaque": 5,
         "degats": "1d12+3", "init_bonus": 0, "nb": 1},
    ],
}
r = client.post("/api/combat/ouvrir", json=corps2, headers=H)
j2 = r.json()
check("ouvrir test-2 -> ok", j2.get("ok") is True, str(j2)[:160])
orque = next(c["cle"] for c in j2["ordre"] if c["nom"].startswith("orque"))
pv_avant = json.loads((perso / "onirios.json").read_text(encoding="utf-8")).get("pv_actuels", -1)
r = client.post("/api/combat/test-2/jet-monstre", json={"attaquant": orque, "cible": "pj:onirios"}, headers=H)
jm = r.json()
check("jet-monstre -> ok", jm.get("ok") is True, str(jm)[:200])
check("jet-monstre -> type attaque", jm.get("type") == "attaque")
check("jet-monstre -> d20 borné", 1 <= jm.get("jet_d20", 0) <= 20)
pv_apres = json.loads((perso / "onirios.json").read_text(encoding="utf-8")).get("pv_actuels", -1)
if jm.get("degats", 0) > 0:
    # Répercussion : la fiche doit avoir baissé (ou le PJ être à 0).
    check("jet-monstre touché -> PV fiche baissés", pv_apres >= 0 and pv_apres < pv_avant,
          f"avant={pv_avant} apres={pv_apres}")
else:
    check("jet-monstre raté -> PV fiche inchangés", pv_apres == pv_avant,
          f"avant={pv_avant} apres={pv_apres}")

# --- cloturer ---
r = client.post("/api/combat/test-1/cloturer", headers=H)
check("cloturer -> ok", r.json().get("ok") is True)

# --- rencontre inconnue ---
r = client.get("/api/combat/introuvable", headers=H)
check("rencontre inconnue -> erreur", r.json()["ok"] is False)

# --- id invalide (traversée) : FastAPI ne route pas (404) ou notre validation ---
r = client.get("/api/combat/..%2F..%2Fetc", headers=H)
rejete = r.status_code == 404 or (r.status_code == 200 and r.json().get("ok") is False)
check("id malveillant -> rejeté", rejete, f"status={r.status_code}")

shutil.rmtree(tmp)
print(f"\n{ok} réussis, {ko} échoués")
raise SystemExit(1 if ko else 0)
