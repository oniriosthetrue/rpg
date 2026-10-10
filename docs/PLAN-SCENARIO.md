# Plan — Gestion des scénarios / campagnes (MJ D&D 5.2.1)

> Projet : `/home/linus/qwen_3.8_vnimanieAI` · Services : `jdr-api` + `open-webui` (`mj-dnd`)
> Docs liées : `dnd/ARCHITECTURE-JDR-OWUI.md`, `dnd/CONTRAT-API-JDR.md` (§13), skill `owui-mj-dnd`
> Statut : **TERMINÉ ET EXÉCUTÉ (code + docs + tests unitaires + test en jeu 13/13).**
> S1 ✅ (moteur
> `dnd_perso/campagne.py` + tests 24/24) ·
> S2 ✅ (router `jdr_api/routers/campagne.py` + persistance `data-campagne/` + montage
> compose — smoke test tous endpoints OK) · S3 ✅ (5 méthodes campagne dans
> `dnd_perso_tool.py`) · S4 ✅ (prompt `/nouveau-scenario` + protocole scénario du
> `mj-systeme.md`) · S5 ✅ (docs : `CONTRAT-API-JDR.md` §13, ce plan, skill) ·
> S6 ✅ **exécuté** (fixture `dnd/scenarios/test-mineur.md` validée + test en jeu
> `tests/live_scenario_owui.py` + runner `tests/run_s6.sh` → **13/13**, 2026-10-10).
> Deux pièges corrigés à l'exécution : (1) image `jdr-api` périmée → rebuild ;
> (2) colonne `tool.specs` périmée → `owui_apply_config.py` régénère désormais `specs`
> automatiquement (voir §Exécution).

---

## 0. Problème à résoudre

Le **scénario** (l'intrigue d'une campagne) vit aujourd'hui **100 % dans le contexte de
conversation** du LLM : accroche, PNJ et leurs attitudes, crochets ouverts/résolus, lieux
découverts, indices trouvés, phase du rythme. Dès que la fenêtre de contexte sature sur
une longue partie, le MJ **oublie ou contredit** sa propre intrigue (un PNJ change de
personnalité, un crochet résolu ressurgit, la « phase » n'a plus de sens).

**Objectif** : déplacer la **structure de la campagne** côté serveur (jdr-api), comme le
combat — *le LLM ne génère pas l'état, il le déclare ; le moteur ne crée pas l'histoire,
il la mémorise*. Le MJ écrit la prose et déclare les événements ; le moteur tient la
structure et la chronologie.

---

## 1. Principe directeur (rappel, non négociable)

- **Le LLM n'invente jamais l'état de la campagne.** Il le **lit** (`etat_de_la_campagne`)
  et le **fait avancer** (`faire_avancer_la_campagne`). La vérité est côté serveur.
- **Le contenu narratif reste au LLM.** Le moteur ne garde que des champs de texte
  opaques (synopsis, accroche, contenu d'un bloc) et la structure du brief.
- **Difficulté = Mode B.** Le moteur **informe** (`advisory_difficulte` : degré + conseil)
  mais ne **décide pas** : il ne modifie jamais stats ni effectifs. Le `danger` de la
  campagne et l'ajustement (`nb`) restent le choix du MJ.
- **Anti-métajeu** : la structure interne (statut d'un crochet, `degre` d'un advisory,
  blocs non déclenchés) ne doit **jamais** être récitée au joueur — le filtre anti-méta
  s'y applique.
- **Le repo reste la source de vérité** ; la base OWUI et l'état de campagne sont
  régénérables / versionnés.

---

## 2. Les 5 principes d'un bon scénario (encodés dans la structure)

1. **Accroche & Enjeux** — raison urgente + ≥2 crochets liés au background d'un PJ.
2. **Structure par Situations (non-linéaire)** — des problèmes, jamais une seule solution ;
   chaque défi a ≥2-3 approches.
3. **Équilibre des 3 Piliers** — Exploration + Interaction Sociale + Combat tactique.
4. **Rythme & Tension (Montagne Russe)** — 4 temps : Accroche ➔ Montée ➔ Climax ➔ Conclusion.
5. **Flexibilité & Impro (Schrödinger's Dungeon)** — blocs d'événements modulaires réutilisables.

| Principe | Champ(s) de la `Campagne` |
|---|---|
| Accroche & Enjeux | `accroche`, `enjeux`, `crochets[].lie_a_pj` |
| Situations non-linéaires | `defis[].approches` |
| 3 Piliers | `lieux[].piliers` ⊆ {exploration, social, combat} |
| Rythme 4 temps | `phase` ∈ accroche→montee→climax→conclusion |
| Blocs modulaires | `blocs[]` (déplaçables via `deplacer_bloc`) |

La structure est **signalée, jamais bloquante** : `etat()` renvoie `structure_valide` +
`avertissements_structure`. Le MJ peut ouvrir un scénario incomplet et le compléter.

---

## 3. Modèle de données — `data-campagne/`

Nouveau dossier **`data-campagne/`** (monté en `rw` comme `data-combat/`), un fichier JSON
par campagne : `data-campagne/campagne-<id>.json`, relu à chaque appel.

Entités (dataclasses `vers_dict`/`depuis_dict`) : `PNJ`, `MonstreScenarise`, `Rencontre`,
`Lieu`, `Defi`, `Crochet`, `Bloc`, regroupées dans `Campagne`. Constantes : `PHASES`,
`DANGERS`, `CROCHETS_STATUTS`, `PILIERS`, `ACTIONS`.

---

## 4. Difficulté = Mode B (moteur informe, scénario décide)

`advisory_difficulte(niveaux_pj, rencontre)` compare le budget d'XP du groupe au CR des
monstres (seuils SRD 5.2.1) → `degre` (tres_facile→mortelle) + `conseil`. Primitive bornée
d'ajustement : l'effectif `nb`. Le moteur ne touche jamais aux stats.

---

## 5. Phases du plan

| Phase | Contenu | Statut |
|---|---|---|
| **S1** | Moteur pur `dnd_perso/campagne.py` (dataclasses, `modifier`, `etat`, `advisory_difficulte`, parseur Markdown stdlib) + `tests/test_campagne.py` | ✅ 24/24 |
| **S2** | Router `jdr_api/routers/campagne.py` (ouvrir/importer/lister/etat/modifier/advisory/cloturer) + `extract.CAMPAGNE_DIR` + montage compose + `main.py` | ✅ smoke test |
| **S3** | 5 méthodes campagne dans `config/openwebui/tools/dnd_perso_tool.py` | ✅ syntaxe OK |
| **S4** | Prompt `/nouveau-scenario` + « Protocole de scénario » dans `mj-systeme.md` | ✅ |
| **S5** | Docs : `CONTRAT-API-JDR.md` §13, ce plan, skill `owui-mj-dnd` | ✅ |
| **S6** | Test en jeu automatisé `tests/live_scenario_owui.py` + runner `tests/run_s6.sh` + fixture `dnd/scenarios/test-mineur.md` (validée par `TestFixtureScenario`) | ✅ exécuté — **13/13** |

---

## 6. Lancement / réinjection (rappel)

- **Stack lancée UNIQUEMENT par l'utilisateur.** L'agent ne fait jamais de test HTTP live
  sans la stack ; les smoke tests appellent les fonctions du routeur en Python direct sur
  un dossier temporaire.
- **⚠️ `jdr-api` est CONSTRUIT (build) et non monté en lecture seule** : son code
  (`jdr_api/`, `dnd_perso/`) est copié dans l'image par `jdr_api/Dockerfile`. Après avoir
  ajouté/modifié un router (ex. `campagne.py`), il faut **reconstruire l'image** sinon le
  conteneur garde l'ancienne et renvoie `404 {"detail":"Not Found"}` sur les nouvelles
  routes :

  ```bash
  docker compose build jdr-api && docker compose up -d jdr-api
  # Vérif : les 7 routes campagne sont déclarées
  docker exec jdr-api python3 -c "from jdr_api.main import app; \
    print([r.path for r in app.routes if 'campagne' in r.path])"
  ```
- **Réinjection OWUI** après édition du tool / des prompts (stack lancée) — la source de
  vérité est le dépôt, on la réinjecte dans la base SQLite d'OWUI. **⚠️ Le modèle ne voit
  pas le `content` du tool : il voit la colonne `tool.specs`** (liste JSON des schémas de
  méthodes, lue à chaque requête). `owui_apply_config.py` **régénère désormais `specs`
  automatiquement** via le parseur officiel d'OWUI (`get_tool_specs`) — sinon ajouter une
  méthode au code ne la rend jamais visible du modèle (piège rencontré en S6 : le modèle
  répondait « je n'ai pas d'outil `ouvrir_une_campagne` » alors que le `content`
  l'contained). Pas besoin de toucher au modèle ni de redémarrer la stack :

  ```bash
  docker exec open-webui rm -rf /tmp/config
  docker cp scripts/owui_apply_config.py open-webui:/tmp/owui_apply_config.py
  docker cp config open-webui:/tmp/config
  docker exec open-webui python3 /tmp/owui_apply_config.py --config-dir /tmp/config/openwebui
  docker exec open-webui rm -rf /tmp/config /tmp/owui_apply_config.py
  # Vérif : les méthodes campagne doivent être dans specs (19 méthodes attendues)
  docker exec open-webui python3 -c "import sqlite3,json; \
    s=json.loads(sqlite3.connect('/app/backend/data/webui.db').execute( \
    'SELECT specs FROM tool WHERE id=\"dnd_perso_tool\"').fetchone()[0]); \
    print(len(s), [m['name'] for m in s if 'campagne' in m['name'] or 'advisory' in m['name']])"
  ```

  Puis **rechargement d'onglet (F5)** dans OWUI — pas de restart de la stack.
- **Test en jeu** (après réinjection, stack lancée) : `bash tests/run_s6.sh`
  (installe le PJ fixture `testerobuste`, lance `live_scenario_owui.py` dans
  `open-webui`, puis nettoie fixture + campagne `test-live-scenario`).
  ⚠️ Les JSON de campagne sont écrits par `jdr-api` (**root**) : le runner les supprime
  via `docker exec jdr-api rm -f /app/data/campagne/…`, sinon « Permission denied » hôte.
  ⚠️ Après `docker compose up -d jdr-api`, attendre « Uvicorn running on … » dans les logs
  avant de lancer le test (sinon `ConnectionRefusedError(111)`).
