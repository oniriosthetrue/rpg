# Checklist de recette UI (SMOKE-UI)

Vérification **manuelle** de l'interface MJ (décision : pas de Playwright).
Chaque point = un parcours complet à valider à la main sur
`https://rpg.minervia.fr` (ou `http://localhost:3000` en dev).

Prérequis : stack lancée (`api` + `web` + `qdrant`), une clé API valide côté
proxy Next (`X-API-Key` injecté serveur, jamais dans le navigateur).

---

## 1. Navigation / layout
- [ ] `/` redirige vers `/chat`.
- [ ] La barre latérale affiche Chat / Persos / Combat / Campagne et navigue entre les pages.
- [ ] Sur mobile (< `md`), le menu ☰ ouvre/referme la navigation.

## 2. Chat — multi-conversations, reset, stop
- [ ] « + Nouvelle conversation » crée une conversation vide ; l'ancienne reste dans la liste.
- [ ] Les conversations persistent après rechargement (localStorage `mj-conversations`).
- [ ] Envoyer un message affiche les tokens en streaming.
- [ ] **Stop** : le bouton ■ interrompt le flux côté client *et* côté serveur
      (`request.is_disconnected()` → le générateur SSE s'arrête, plus de tokens en amont).
- [ ] Supprimer une conversation la retire de la liste sans casser les autres.

## 3. Citations RAG
- [ ] Une question de règles fait apparaître un bloc dépliable « Sources / Citations »
      sous la réponse, avec nom de fiche + source (ex. « SRD 5.2.1 p.170 »).
- [ ] Sans réponse du RAG (Qdrant vide/éteint), le chat répond quand même (le RAG ne bloque jamais).

## 4. Personnages (`/persos`)
- [ ] La liste des PJ se charge ; « + Créer » ouvre le wizard guidé.
- [ ] Le wizard mène une création pas-à-pas jusqu'à `/finaliser` (fiche persistée).
- [ ] Sélectionner un PJ affiche sa fiche ; les actions (soigner, dégâts, XP, or,
      objet, apprendre un sort) mettent à jour la fiche (PATCH) et se reflètent au retour.
- [ ] Le PJ actif est partagé avec le chat (contexte `mj-perso-actif`).

## 5. Combat (`/combat`)
- [ ] La liste des rencontres se charge (`GET /api/combat`).
- [ ] Ouvrir une rencontre (PJ présents + monstres JSON) lance l'initiative et affiche le tableau.
- [ ] Le combattant « actif » est surligné ; « ▶ Tour suivant » fait avancer l'initiative.
- [ ] « Attaque (serveur) » (monstre) et « Attaque (mon d20) » (PJ) produisent un jet.
- [ ] − PV / + PV / Condition sur un combattant mettent à jour PV et conditions.
- [ ] Les dégâts sur un PJ se répercutent sur sa fiche ; « Clôturer » rend la rencontre inactive.

## 6. Campagne (`/campagne`)
- [ ] La liste des campagnes se charge (`GET /api/campagne`).
- [ ] Importer un scénario Markdown à front-matter crée la campagne et affiche son état.
- [ ] Si la structure est incomplète, les avertissements s'affichent (jamais bloquants).
- [ ] Les mutations fonctionnent : phase suivante, résoudre un crochet, rencontrer /
      attitude d'un PNJ, découvrir un lieu, activer/réserver un bloc, ajouter indice / récompense.
- [ ] L'advisory d'équilibrage (monstres JSON ± niveaux) renvoie degré + conseil.
- [ ] « Clôturer » rend la campagne inactive.

---

## Régression backend (à chaque déploiement)
```bash
export PYTHONPATH="$PWD/apps/api:$PWD/packages"
export DND_CORPUS_DIR="$PWD/packages/corpus/srd-5.2.1"
PYDANTIC_AI_NO_BANNER=1 .venv/bin/python -m unittest \
  tests.test_combat tests.test_campagne tests.test_dnd_perso tests.test_agent \
  tests.test_ui_routes
# → « Ran 72 tests … OK »
```
