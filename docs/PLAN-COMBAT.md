# Plan — Gestion des combats (MJ D&D 5.2.1)

> Projet : `/home/linus/qwen_3.8_vnimanieAI` · Services : `jdr-api` + `open-webui` (`mj-dnd`)
> Docs liées : `dnd/ARCHITECTURE-JDR-OWUI.md`, `dnd/CONTRAT-API-JDR.md`, skill `owui-mj-dnd`
> Statut : **EN COURS.** C1 ✅ · C2 ✅ · C2b ✅ · C3 ✅ (moteur + tests + arène +
> API router + persistance `data-combat/` + montage compose — smoke test 29/29,
> `jdr-api` reconstruit et validé en live 20/20) · C4 ✅ (7 méthodes de combat
> dans `dnd_perso_tool.py`, 2 copies, réinjectées OWUI et vérifiées en base).
> C5 ✅ (protocole combat + filtre anti-méta v2.3). **C6 ✅** (test en jeu automatisé
> 10/10, 2026-10-09 — `tests/live_combat_owui.py`). Plan combat terminé.
> Hors du plan A/B/C/D (qui est terminé).

---

## 0. Problème à résoudre

Aujourd'hui le combat est **piloté à 100 % par le LLM** (prompt `mj-systeme.md`, mode
« tacticien »). Seuls les PV **du joueur** sont persistés (`modifier_personnage` →
`degats`/`soigner`). Tout le reste — ordre d'initiative, tours, **PV des monstres**,
conditions — vit dans le **contexte de conversation** et se perd / dérive dès que la
fenêtre de contexte sature sur un combat long.

**Objectif** : déplacer l'**état de rencontre** et les **jets** côté serveur (jdr-api),
comme le veut la règle d'or — *le LLM ne calcule rien, il demande, lit et raconte*.

---

## 1. Principe directeur (rappel, non négociable)

- **Le LLM ne lance jamais les dés.** Pour le joueur, c'est le **joueur** qui lance et
  communique son résultat. Pour les **monstres/PNJ**, c'est le **serveur** qui lance
  (via `dnd_perso.dice.roll`) et renvoie le résultat tout fait au MJ.
- **Le LLM ne calcule aucune statistique.** CA, PV max, bonus d'attaque, dégâts,
  sauvegardes : tout vient de la **fiche RAG** du monstre ou de la **fiche** du joueur.
- **Anti-métajeu** : le serveur renvoie les PV d'un monstre au MJ, mais le **filtre
  anti-méta** doit continuer à interdire leur divulgation au joueur (on ne montre que
  les effets narrés).
- **Le repo reste la source de vérité** ; la base OWUI et l'état de combat sont
  régénérables / versionnés.

---

## 2. Modèle de données — « état de rencontre »

Nouveau dossier de données **`data-combat/`** (monté en `rw` comme `data-perso/`),
un fichier JSON par campagne/rencontre active : `data-combat/rencontre-<id>.json`.

```jsonc
{
  "v": 1,
  "id": "rencontre-2026-10-09-grotte",
  "titre": "Embuscade dans la grotte",
  "active": true,
  "tour": 1,
  "ordre": [                       // trié par initiative décroissante (résolution SRD §)
    { "cle": "pj:onirios", "nom": "Onirios", "camp": "pj", "initiative": 14,
      "initiative_jeu": 12, "pv": 6, "pv_max": 6, "ca": 11, "conditions": [] },
    { "cle": "mon:0:gobelin", "nom": "Gobelin", "camp": "monstre", "initiative": 9,
      "initiative_jeu": 7, "pv": 7, "pv_max": 7, "ca": 15, "conditions": [] }
  ],
  "index_joueur_actif": 0,         // qui doit jouer maintenant
  "cree_le": "2026-10-09T14:00:00"
}
```

- **`cle`** = identifiant stable (`pj:<nom>` ou `mon:<index>:<nom>`).
- Les **monstres** sont saisis à l'ouverture depuis la **fiche RAG** (PV, CA, bonus
  d'attaque, dés de dégâts, initiative) — jamais inventés.
- Persistance = fichiers JSON (relis à chaque appel), comme les fiches perso.

---

## 3. Règles SRD 5.2.1 à coder (source : `01-chapitres/08-regles-de-combat.md`)

| Règle | Implémentation serveur |
|---|---|
| **Initiative** | `d20 + mod_Dex` (PJ) / valeur de la fiche (monstre). Le serveur lance. |
| **Ordre** | tri décroissant ; égalité → le MJ départage (paramètre). |
| **Attaque** | `d20 + bonus` vs CA → touché/échec. Le serveur lance pour les monstres. |
| **Critique** | `nat 20` → dés de dégâts doublés (jet des dès ×2, pas le modificateur). |
| **Dégâts** | `NdM + mod` renvoyés ; appliqués aux PV de la cible. |
| **Sauvegarde** | `d20 + mod_carac + (maîtrise si applicable)` vs DD. |
| **Conditions** | liste de statuts par combattant (aveuglé, empoisonné…). |

> ⚠️ **Périmètre** : on code l'**arithmétique** (jets, PV, CA, critique). On **ne code
> pas** la sémantique complète des conditions (chaque condition = règle textuelle du
> RAG que le MJ applique). Les conditions sont **stockées/affichées**, pas simulées.

---

## 4. Nouveaux endpoints jdr-api (`jdr_api/routers/combat.py`)

Monté dans `main.py` (`app.include_router(combat.router)`). Enveloppe `enveloppe()` +
`autorise(x_api_key)` identiques aux autres routes.

| Méthode + chemin | Rôle | Corps / params |
|---|---|---|
| `POST /api/combat/ouvrir` | Ouvre une rencontre, calcule les initiatives (le serveur lance les d20). | `{titre, combattants:[{type:"pj",nom} \| {type:"monstre",nom,pv,ca,init_bonus,attaque,degats,nb}×]}` |
| `GET  /api/combat/{id}` | État complet de la rencontre (ordre, tour, qui joue). | — |
| `POST /api/combat/{id}/jet-monstre` | Le serveur lance attaque+dégâts d'un monstre contre une cible. | `{attaquant:"mon:0:gobelin", cible:"pj:onirios"}` |
| `POST /api/combat/{id}/jet-joueur` | Enregistre le résultat annoncé par le joueur (le serveur ne lance pas). | `{attaquant:"pj:onirios", cible, de_attaque, de_degats}` |
| `POST /api/combat/{id}/tour-suivant` | Avance d'une case dans l'ordre d'initiative. | — |
| `PATCH /api/combat/{id}` | Dégâts/soins/conditions sur n'importe quel combattant. | `{cle, action:"degats"\|"soigner"\|"condition", valeur}` |
| `POST /api/combat/{id}/cloturer` | Clôture (PV du PJ déjà persistés via la fiche). | — |

**Cohérence PJ** : quand un PJ reçoit des dégâts en combat, l'endpoint **répercute**
aussi sur la fiche (`mj.modifier_personnage(nom,[{"action":"degats",...}])`) pour que
`onirios.json` reste la vérité des PV hors combat. Un seul chemin d'écriture des PV PJ.

---

## 5. Nouvelles méthodes d'outil (`config/openwebui/tools/dnd_perso_tool.py`)

Mêmes méthodes minces qui relaient vers jdr-api (comme `charger_le_personnage`) :

- `ouvrir_un_combat(titre, combattants)` → `POST /ouvrir`
- `etat_du_combat(id)` → `GET /{id}`
- `lancer_le_jet_d_un_monstre(id, attaquant, cible)` → `POST /jet-monstre`
- `enregistrer_le_jet_du_joueur(id, attaquant, cible, de_attaque, de_degats)` → `POST /jet-joueur`
- `tour_suivant(id)` → `POST /tour-suivant`
- `appliquer_au_combat(id, cle, action, valeur)` → `PATCH /{id}`
- `clore_le_combat(id)` → `POST /cloturer`

> La tool ne calcule rien : elle appelle et renvoie le JSON du serveur.

---

## 6. Prompt système (`config/openwebui/prompts/mj-systeme.md`) ✅ FAIT (C5)

Remplacer la puce « Combat (tacticien) » par un **protocole de combat** explicite :

1. **Ouverture** : lister les adversaires **avec leurs stats lues dans le RAG**, puis
   `ouvrir_un_combat(...)`. Le serveur rend l'ordre d'initiative.
2. **Tour du joueur** : demander le jet (attaque + dégâts), puis
   `enregistrer_le_jet_du_joueur(...)`.
3. **Tour d'un monstre** : `lancer_le_jet_d_un_monstre(...)` — le serveur lance et rend
   touché + dégâts ; le MJ **raconte** sans révéler les PV du monstre.
4. **Avancement** : `tour_suivant(...)` à chaque fin de tour.
5. **Mort/fuite** : `clore_le_combat(...)`.
6. Rappel anti-métajeu : ne jamais énoncer les PV/ca cachés d'un monstre.

---

## 7. Filtre anti-méta (`config/openwebui/filters/filtre_anti_meta_mj.py`) ✅ FAIT (C5, v2.3)

Vérifier/étendre pour que les champs sensibles renvoyés par les nouveaux endpoints
(`pv` des monstres, `ca` des monstres dans `[MÉCANIQUE]`) ne fuient pas vers le joueur.
Le MJ ne doit voir ces chiffres que pour **narrer**, jamais les citer.

---

## 8. Phases d'exécution

| Phase | Contenu | Critère de fin |
|---|---|---|
| **C1 — Modèle & données** ✅ | dataclass `Rencontre`/`Combattant` (`dnd_perso/combat.py`) + sérialisation JSON. *(Le montage `data-combat/` dans compose reste à faire en C3, au moment du redémarrage.)* | Une rencontre s'ouvre/relit/fichier valide. **Fait.** |
| **C2 — Moteur de jets** ✅ | `dnd_perso/combat.py` : initiative, attaque vs CA, critique, dégâts, sauvegarde (réutilise `dice.roll`). Tests unitaires `tests/test_combat.py` (15 tests). | Jets reproductibles via `--seed` ; critique correct. **Fait — 15/15.** |
| **C2b — Arène de test** ✅ | `scripts/arena.py` : simulation headless de N combats (moteur seul, sans OWUI ni LLM), stats agrégées. Voir §8bis. | 1000 combats reproductibles via `--seed` ; courbes/taux cohérents ; non-régression. **Fait.** |
| **C3 — API** ✅ | `jdr_api/routers/combat.py` (7 routes) + branchement `main.py` + `COMBAT_DIR` (`extract.py`) + montage `data-combat/` (compose + `.gitkeep`) + répercussion PV PJ sur la fiche. `dice.py` : support `NdM±K` + `decomposer()` (le critique double les dès, pas le modificateur). | Smoke test `tests/smoke_combat_api.py` (TestClient, 29/29, stable 15×) + `test_combat.py` (15/15). **Fait — redémarrage `jdr-api` en attente (utilisateur).** |
| **C4 — Outil** ✅ | 7 méthodes dans `dnd_perso_tool.py` (2 copies) + réinjection OWUI (injecteur idempotent). | ✅ `ouvrir_un_combat`, `etat_du_combat`, `lancer_le_jet_d_un_monstre`, `enregistrer_le_jet_du_joueur`, `tour_suivant_du_combat`, `appliquer_au_combat`, `clore_le_combat` — vérifiées en table `tool` (id `dnd_perso_tool`). |
| **C5 — Prompt & filtre** ✅ | Protocole de combat dans `mj-systeme.md` (ouvrir→jet PJ→jet monstre→tour-suivant→appliquer→clore, règle d'or « le MJ ne calcule rien ») + filtre anti-méta **v2.3** (clause combat dans la directive invisible + `_masquer_stats_monstre` qui masque `CA`/`PV` en bloc de stats, sans toucher aux valeurs différentielles). Réinjecté, vérifié en base. | ✅ Le MJ déroule un combat complet sans calculer lui-même. **Fait.** |
| **C6 — Test en jeu** ✅ | `tests/live_combat_owui.py` (conduit le vrai chat OWUI via `chat/completions`, JWT admin) + `tests/run_c6.sh` (runner hôte : installe le PJ fixture `testerobuste`, lance dans `open-webui`, nettoie). Scénario enlisement : PJ Barbare CA 25 / 17 PV contre 1 gobelin (CA 15, 10 PV, +4) ; le pilote annonce toujours d20=2 au PJ → il rate → PV gobelin stables, le PJ tient 6+ tours. | ✅ **10/10** (2026-10-09) : combat ouvert via `ouvrir_un_combat`, tour ≥ 6 atteint, PV monstres stables (=10), PV PJ cohérents fiche (répercussion), **persistance relue après reset de contexte** (nouvelle conversation → `etat_du_combat` cite le bon tour), clôture ok. |

---

## 8bis. Arène de test (C2b) — validation déterministe du moteur

**Pourquoi** : C6 (test en jeu) est non-déterministe et lent (JWT, `chat/completions`,
LLM qui peut ne pas appeler le tool, fenêtre de contexte). Il ne peut **pas** valider
l'arithmétique du moteur de façon fiable. L'arène isole le **moteur pur**
(`dnd_perso/combat.py`) **sans OWUI ni LLM**, avant de brancher le modèle.

**Ce qu'elle prouve** : l'initiative trie correctement, `nat 20` double les dés de
dégâts (pas le modificateur), les PV descendent jusqu'à 0 et s'arrêtent là,
`tour_suivant` boucle sur l'ordre, une rencontre se clôture. Coût quasi nul :
`dice.roll(expr, rng)` est **déjà seedé**, le moteur est une fonction pure.

**Interface** (CLI, stdlib uniquement) :

```bash
python3 scripts/arena.py --pj onirios --monstre gobelin --nb 1000 --seed 42
#   PJ lu depuis data-perso/, monstre lu depuis sa fiche RAG (04-monstres/)
#   → 1000 combats simulés, jets lancés par dice.roll (rng seedé)
```

**Sorties agrégées** :
- taux de victoire PJ / monstre / nul (plafond de tours)
- nombre de tours : moyen / min / max
- % de coups critiques (PJ et monstre)
- PV restants du PJ à la victoire (distrib.)
- détection d'**équilibrage** : un Mag niv 1 qui gagne 100 % contre un gobelin = bug de CA.

**Design** :
- `arena.py` **n'importe que `dnd_perso`** (pas FastAPI, pas HTTP) → testable hors stack,
  sans redémarrage, dans le repo.
- Lit le PJ via `dnd_perso.extract`/`models`, le monstre via la fiche Markdown du corpus
  (parse PV/CA/attaque/dégâts) — même source que le MJ.
- Boucle : `ouvrir` → tant qu'aucun camp à 0 PV et tours < plafond : attaque du
  combattant actif → `tour_suivant`. 100 % via le moteur, 0 % de calcul dans le script.
- **Non-régression** : `--seed` fixe → sortie identique d'une exécution à l'autre ;
  à versionner comme référence (`tests/reponses-arena-*.md`).

**Distinction** : l'**arène en jeu** (`/arene` dans OWUI, sparring contre un monstre)
reste **hors périmètre** (§10) — confort joueur, redondant avec le combat normal,
sans garantie sur le moteur.

---

## 9. Contraintes d'implémentation (rappel du skill)

- **Ne JAMAIS restart la stack** (l'utilisateur seul lance/relance). L'ajout du montage
  `data-combat/` dans `docker-compose.yml` et le nouveau router exigent un **redémarrage
  de `jdr-api`** → à faire **par l'utilisateur**, pas par l'agent.
- **Repo = source de vérité** : après édition DB OWUI, simple **F5**.
- Avant `docker cp config ...` : `docker exec open-webui rm -rf /tmp/config`.
- Réinjecter via `scripts/owui_apply_config.py` (idempotent).
- `data-combat/` doit être **couvert par `backup-stack.sh`** (comme `data-perso/`).

---

## 10. Hors périmètre (pour l'instant)

- Simulation automatique des **conditions** (statuts) — stockage/affichage seulement.
- **Multi-joueurs** (canal = table de jeu) — renvoyé à ARCHITECTURE §9.
- **Arenas tactiques / portée / couverture** — abstraction narrative, pas de grille.
- **Arène en jeu `/arene`** (sparring dans OWUI) — reporter ; l'arène de **test** (§8bis)
  est headless et suffit à valider le moteur.
- **Flux d'initiative automatisé des sorts** (concentration, durées) — phase ultérieure.
