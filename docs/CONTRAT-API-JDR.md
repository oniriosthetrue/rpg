# Contrat JSON — API JDR (règles D&D 5.2.1 SRD)

> **But** : figer le contrat entre le backend de règles (`dnd_perso` + API REST)
> et ses clients (Open WebUI aujourd'hui, toute autre interface demain).
> **Règle d'or** : le LLM raconte, le backend calcule. Tout ce qui touche aux
> règles (création, dés, fiche, inventaire) passe par l'API ; le client ne fait
> que relayer les JSON, mot pour mot.

- Version du contrat : **v1** (champ `v` dans chaque réponse).
- Corpus de référence : SRD 5.2.1 FR (`dnd/srd-5.2.1/`, `edition: srd-5.2.1`).
- Encoding : UTF-8, JSON uniquement (`Content-Type: application/json`).
- Base : `http://jdr-api:8000` (réseau docker `mynetwork`) — **jamais exposé sur Internet** par défaut.

---

## 1. Enveloppe de réponse (universelle)

TOUTE réponse de l'API a cette forme :

```json
{
  "ok": true,
  "v": 1,
  "type": "question",
  "...": "champs spécifiques au type"
}
```

| champ  | type   | règle |
|--------|--------|-------|
| `ok`   | bool   | `false` **seulement** pour `type: "erreur"`. Le client doit le vérifier en premier. |
| `v`    | int    | version du contrat (`1`). Inchangée tant que les champs existants ne sont ni retirés ni renommés. |
| `type` | enum   | voir §2. Le client se branche **uniquement** sur ce champ. |

Règles pour le client (OWUI ou autre) :

1. Relayer `question`, `options`, `fiche` **verbatim** (pas de reformulation par le LLM).
2. Ne jamais inventer de valeur de `type` ni de contenu de `options` : elles viennent du backend.
3. En cas d'`ok: false`, transmettre `erreur` honnêtement, ne pas réessayer en boucle.

---

## 2. Les `type` de réponse (enum fermé)

| `type`      | émis par        | sens |
|-------------|-----------------|------|
| `question`  | `/creation/*`   | le backend pose une question ; `options` = choix valides. |
| `fiche`     | `/creation/*`   | création terminée, la fiche est prête (fin d'interview). |
| `abandon`   | `/creation/*`   | le joueur a abandonné ; plus rien à faire. |
| `options`   | `/creation/options` | liste de options d'une étape (demande explicite du joueur). |
| `personnage`| `/personnages/*`| une fiche stockée (chargement, modification). |
| `liste`     | `/personnages`  | tableau de fiches (résumées). |
| `erreur`    | partout         | échec ; `ok: false` + message. |

> ⚠️ Décision de standardisation : la fin de création est `type: "fiche"`
> (le code actuel de `mj.py` renvoie bien `"fiche"` ; le prompt
> `nouveau-perso.md` dit `final` → **le prompt sera corrigé**, pas l'inverse).

---

## 3. Fin de création — `type: "fiche"`

```json
{
  "ok": true,
  "v": 1,
  "type": "fiche",
  "message": "La fiche est prête. Vous pouvez encore demander des modifications.",
  "fiche": "<corps markdown de la fiche>",
  "personnage": { "...": "voir §8 — structure canonique" },
  "sauvegarde": true,
  "fichier": "/app/data/perso/<nom>.json",
  "avertissements": ["Certains choix ont été tirés au hasard."]
}
```

- `fiche` : markdown prêt à afficher (convention corpus : pas de `<<<FICHE>>>` dans
  ce champ, uniquement le corps ; l'API garde l'entête pour elle).
- `personnage` : **la source de vérité** (dict complet, §8). C'est lui qui est
  stocké, pas le markdown.
- `avertissements` : liste (éventuellement vide) de ce que le backend a décidé
  seul (tirages au hasard…). Le client doit la mentionner honnêtement.

---

## 4. Endpoints — création guidée

| Méthode + chemin | Corps de la requête | Réponse |
|---|---|---|
| `POST /api/creation` | `{"seed": 123?}` (facultatif) | `type: "question"` (première question) |
| `POST /api/creation/{chat_id}/reponse` | `{"reponse": "<réponse libre du joueur>"}` | `question` \| `fiche` \| `abandon` \| `erreur` |
| `POST /api/creation/{chat_id}/abandon` | — | `type: "abandon"` \| `erreur` |
| `GET  /api/creation/{chat_id}/etat` | — | `type: "etat"` (diagnostic interne) |
| `GET  /api/creation/{chat_id}/options?etape=classe` | — | `type: "options"` |

- `chat_id` : id de conversation OWUI (opaque pour l'API). Une création = une conversation.
- `reponse` : **langage libre**, le backend normalise et reconnait lui-même
  (le client ne pré-digeste pas). Réponses spéciales reconnues par le backend :
  « au hasard », « abandonne », « oui »/« non » (finalisation).
- Si `erreur: "Aucune création en cours…"` → le client doit proposer `/nouveau-perso`.

Exemple de `type: "question"` :

```json
{
  "ok": true, "v": 1, "type": "question",
  "etape": "classe",
  "question": "Commençons par la classe : qu'aimeriez-vous jouer ?",
  "options": ["Barbare", "Barde", "Clerc", "..."],
  "progression": "1/9",
  "avertissements": []
}
```

Exemple de `type: "options"` :

```json
{
  "ok": true, "v": 1, "type": "options",
  "etape": "competences",
  "question": "Quelles compétences choisissez-vous ?",
  "options": ["Arcanes", "Athlétisme", "..."]
}
```

---

## 5. Endpoints — gestion des personnages (post-création)

| Méthode + chemin | Corps | Réponse |
|---|---|---|
| `GET  /api/personnages` | — | `type: "liste"` |
| `GET  /api/personnages/{nom}` | — | `type: "personnage"` |
| `PATCH /api/personnages/{nom}` | `{"actions": [...]}` | `type: "personnage"` (fiche recalculée) |
| `DELETE /api/personnages/{nom}` | — | `{"ok": true, "type": "supprime"}` |

`GET /api/personnages` → `type: "liste"` :

```json
{
  "ok": true, "v": 1, "type": "liste",
  "personnages": [
    {"nom": "Didier_Petitpas", "espece": "Halfelin", "classe": "Roublard",
     "niveau": 1, "pv": 7, "modifie_le": "2026-09-24T17:30:00Z"}
  ]
}
```

`GET /api/personnages/{nom}` → `type: "personnage"` :

```json
{
  "ok": true, "v": 1, "type": "personnage",
  "fiche": "<corps markdown>",
  "personnage": { "...": "§8" },
  "modifie_le": "2026-09-24T17:30:00Z"
}
```

`PATCH /api/personnages/{nom}` — **actions fermées**, pas de JSON libre :

```json
{
  "actions": [
    {"action": "soigner",    "valeur": 5},
    {"action": "degats",     "valeur": 3, "critique": false},
    {"action": "ajouter_or", "valeur": 50},
    {"action": "ajouter_objet", "valeur": "Corde de soie (10 m)"},
    {"action": "apprendre_sort", "valeur": "Bouclier"},
    {"action": "lancer_sort", "valeur": "Bouclier", "niveau": 1},
    {"action": "repos_long"},
    {"action": "gagner_xp",  "valeur": 300},
    {"action": "changer_alignement", "valeur": "Loyal Bon"}
  ]
}
```

Règles :
- Le backend **recalcule tout** ce qui est dérivé (PV max, CA, mods, sorts
  débloqués au passage de niveau…) — le client n'envoie **jamais** de valeurs calculées.
- Une action inconnue → `erreur` (pas d'ignorance silencieuse).
- `degats`/`soigner` ajustent `pv` (plafonné au max, plancher 0 + `à_la_mort: true` si 0).
- `gagner_xp` peut déclencher un passage de niveau (le backend gère la table).
- `lancer_sort` **consomme un emplacement de sort** : `valeur` = nom du sort,
  `niveau` optionnel (sinon lu dans le corpus ; `0` = tour de magie, jamais
  consommé). Le max par niveau est dérivé de la classe + du niveau (table
  d'incantation SRD) ; seul l'usage est stocké. Si aucun emplacement du niveau
  requis (ou supérieur) n'est libre → `erreur` « Plus d'emplacement… ».
- `repos_long` remet à zéro tous les compteurs d'emplacements consommés.
- Réponse : un `type: "personnage"` complet (la fiche à jour), + `modifications`
  listant ce qui a été appliqué (pour honnêteté envers le joueur).

---

## 6. Erreurs — `type: "erreur"`

```json
{"ok": false, "v": 1, "type": "erreur", "erreur": "Aucune création en cours : utilisez /nouveau-perso pour commencer."}
```

Codes (dans `erreur`, préfixe stable) :
- `Aucune création en cours…` → le client doit relancer `/nouveau-perso`.
- `Étape inconnue : …` → bug client (ne jamais laisser l'utilisateur voir ça tel quel).
- `Personnage introuvable : …` → proposer la liste (`GET /api/personnages`).
- `Valeur invalide : …` → l'action PATCH n'a pas pu être appliquée.

---

## 7. Auth (si exposée au-delà de `mynetwork`)

- Header `X-API-Key: <token>` sur toutes les requêtes.
- Par défaut l'API n'est **pas** exposée (pas de label Traefik, pas de Caddy) :
  seuls les conteneurs de `mynetwork` y accèdent.
- Si un jour exposition publique (`jdr.minervia.fr`) : clé obligatoire + HTTPS Caddy,
  et **jamais** de liste exhaustive des personnages en accès non authentifié.

---

## 8. Structure canonique du personnage (`personnage`)

C'est LE contrat entre backend et clients. Toute évolution ajoute des champs,
ne renomme ni ne retire rien sans changer `v`.

```json
{
  "nom": "Didier Petitpas",
  "espece": "Halfelin",
  "classe": "Roublard",
  "historique": "Artisan",
  "alignement": "Neutre",
  "niveau": 1,
  "carac": {"Force": 8, "Dextérité": 15, "Constitution": 14, "Intelligence": 10, "Sagesse": 12, "Charisme": 13},
  "mods": {"Force": -1, "Dextérité": 2, "Constitution": 2, "Intelligence": 0, "Sagesse": 1, "Charisme": 1},
  "competences": [{"nom": "Discrétion", "maitrisee": true}],
  "langues": ["Commun", "Halfelin"],
  "equipement": ["Dague", "Tenue commune", "Une petite cloche en laiton"],
  "sorts": ["Tour de magie", "Bouclier"],
  "emplacements_utilises": {"1": 1},
  "emplacements": {"1": {"max": 2, "utilises": 1, "restants": 1}},
  "bonus_maitrise": 2,
  "pv": 11,
  "initiative": 2,
  "ca": 14
}
```

Règles :
- `carac` : 6 clés fixes (accents inclus). `mods` : mêmes 6 clés, entiers signés.
- `competences` : objets `{nom, maitrisee}` — **jamais** de liste de chaînes.
- `langues` / `sorts` : listes de chaînes (noms exacts du corpus).
- `emplacements_utilises` : `{niveau_de_sort: nb_consommes}` (entier, stocké).
  `emplacements` : vue dérivée `{niveau: {max, utilises, restants}}` — le `max`
  vient de la table d'incantation (classe + niveau), absent pour une classe non
  lanceuse. Les tours de magie (niveau 0) ne consomment jamais d'emplacement.
- `equipement` : liste de chaînes (une ligne = un objet, l'or en « 50 po »).
  **La babiole fait partie de l'équipement** : c'est le dernier objet de la liste
  (règle SRD : la babiole est un objet porté). Il n'y a **pas** de champ `babiole`
  séparé ; les anciennes fiches qui l'ont sont fusionnées dans `equipement` à la
  lecture par `depuis_dict()`.
- `pv` : **PV courants** (modifiables) ; le max est dérivé (dé de vie + mod CON).
- Champs calculés (`mods`, `pv`, `initiative`, `ca`) : en lecture seule pour le client.
- `a_la_mort: true` (booléen, ajouté seulement si `pv == 0`).

---

## 9. Conventions transverses

- **Le client ne calcule rien** : pas de jets, pas de modificateurs, pas de tables.
- **Le backend ne parle pas au joueur** : il renvoie des JSON ; c'est le MJ (LLM)
  qui humanise, mais `question`/`options`/`fiche` sont relayés verbatim.
- **Une session = un chat** : `chat_id` OWUI = clé de session. Les sessions
  durent le temps de la création ; la fiche, elle, est persistée (volume `data-perso/`).
- **Compatibilité** : on ajoute des champs, on ne retire/renomme pas avant `v: 2`.
- **Idempotence** : `GET` sans effet de bord ; `PATCH` = actions additives ou
  correctives explicites, jamais « remplace tout le personnage ».

---

## 10. Exemple de dialogue (référence client)

1. Joueur : « /nouveau-perso » → client : `POST /api/creation` → `question` (classe).
2. Joueur : « je joue un barde » → client : `POST …/reponse {"reponse": "je joue un barde"}`
   → backend reconnaît « Barde », pose `competences`.
3. Joueur : « quelles sont les compétences dispo ? » → `GET …/options?etape=competences` → `options`.
4. Joueur : « au hasard » → `POST …/reponse {"reponse": "au hasard"}` → tout est tiré,
   `avertissements` non vide → à la fin `type: "fiche"`.
5. Aventure : « je soigne Didier de 5 PV » → `PATCH /api/personnages/Didier_Petitpas`
   `{"actions":[{"action":"soigner","valeur":5}]}` → `personnage` (fiche à jour).

---

## 11. À faire côté code (rappel, pas le contrat lui-même)

- [ ] `dnd_perso/extract.py` : `PERSO_DIR` via env `DND_PERSO_DIR` (défaut actuel conservé).
- [ ] `dnd_perso/models.py` : `Personnage.depuis_dict()` (pour `PATCH`) ; la babiole est
  fusionnée dans `equipement` (accepter un champ `babiole` legacy à l'entrée).
- [ ] `mj.py` `_finaliser` : ajouter la babiole à `equipement` (plus de champ `babiole`
  séparé) ; `export.py` : supprimer la section « Babiole » de `en_markdown`.
- [ ] `openui/mj.py` : `lister_personnages` / `charger_personnage` / `modifier_personnage`
  + `export.sauvegarder()` dans `personnage_final` ; corriger `type: "fiche"` (déjà bon)
  et **le prompt** `nouveau-perso.md` qui dit `final`.
- [ ] `openui/tools/dnd_perso_tool.py` : client HTTP (`urllib`) vers `http://jdr-api:8000`.
- [ ] `docker-compose.yml` : service `jdr-api` + volume `./data-perso:/app/data/perso` (rw).

---

## 12. Combat — qui décide quoi (scénario vs moteur)

> **Règle de partage** (prolongement de la règle d'or) : **le scénario pilote le
> « quoi », le moteur pilote le « comment ça se résout ».** Le MJ (LLM) *choisit*
> l'action d'un monstre (quel pouvoir, quelle cible, fuir ou pas) ; le moteur
> *résout* cette action (jet, CA, critique, dégâts, PV) et détient l'état.

### 12.1 Répartition des responsabilités

| Décision / opération | Propriétaire | Où ça vit |
|---|---|---|
| **Comportement tactique** (ciblage, fuir à PV bas, garder une ressource, protéger la concentration) | **Scénario (MJ/LLM)** | prompt système + fiche RAG du monstre (« Comportement en combat ») |
| **Quel pouvoir / action employer** | **Scénario (MJ/LLM)** | lecture de la fiche RAG, choix contextuel |
| **Statistiques du monstre** (PV, CA, bonus d'attaque, dés de dégâts, init) | **Fiche RAG → fournie à l'API** | `POST /api/combat/ouvrir` (le moteur ne les invente jamais) |
| **Résolution mécanique** (d20+bonus vs CA, nat 20/1, `NdM+mod`, dés doublés au critique, PV ≥ 0) | **Moteur** | `dnd_perso/combat.py` |
| **État de rencontre** (ordre d'initiative, tour courant, PV, conditions) | **Moteur** | `data-combat/<id>.json` |
| **Conditions / statuts** | **Moteur (stockage/affichage seulement)** | leur *sémantique* reste une règle textuelle du RAG que le MJ applique |

**Ce qu'il ne faut jamais faire :**
- ❌ Coder l'IA d'un monstre dans le moteur (`if monstre == "loup": …`) → le moteur
  devient un DM scripté et rigide.
- ❌ Laisser le LLM *résoudre* jets/dégâts/PV → jets inventés, PV qui dérivent,
  perte de reproductibilité.

### 12.2 Les pouvoirs = **données de la fiche**, pas logique codée

Un monstre peut avoir plusieurs actions (morsure, griffe, arc, cracheur de feu…).
Chacune est une **primitive paramétrée** que le MJ déclare et que le moteur résout.
À l'ouverture, on ne passe qu'**une** action principale par spéc de monstre ; si un
monstre a plusieurs pouvoirs, le MJ **rouvre/ajuste** via `PATCH` ou déclare
l'action au moment du jet (§12.3).

```jsonc
// POST /api/combat/ouvrir — combattants[] (extrait)
{
  "type": "monstre",
  "nom": "Gobelin",
  "pv": 10, "ca": 15,
  "attaque": 4,          // bonus d'attaque (lu dans la fiche RAG)
  "degats": "1d6",       // expression des dés (le moteur lance, pas le MJ)
  "mod_degats": 2,
  "init_bonus": 2,
  "nb": 3                // 3 exemplaires numérotés (Gobelin 1/2/3)
}
```

> Les champs `attaque`/`degats`/`mod_degats`/`init_bonus` sont **fournis par le MJ**
> (lus dans la fiche RAG). Le moteur ne les déduit pas du nom du monstre.

### 12.3 Flux d'une action de monstre (le MJ déclare, le moteur résout)

```
MJ (scénario)  →  « le Gobelin 2 mord le Clerc »  (intent : attaquant + cible)
        ↓  POST /api/combat/{id}/jet-monstre  {attaquant, cible}
Moteur         →  roller_attaque()  →  {jet, touche, critique, degats, pv_restants}
        ↓  (PV du PJ répercutés sur sa fiche par le serveur)
MJ (scénario)  →  narrativise le résultat renvoyé, verbatim sur les chiffres
```

- **`jet-monstre`** : le moteur **lance** le d20 et les dégâts (le monstre est
  « mené » par le serveur). Réservé aux `camp == "monstre"`.
- **`jet-joueur`** : le joueur **annonce** son d20 (`de_attaque`) ; le serveur ne
  le relance pas, il *résout* contre la CA et applique les PV. `de_degats` optionnel
  (sinon le moteur lance les dés du PJ).
- **`PATCH /api/combat/{id}`** : ajustements hors attaque — `degats`, `soigner`,
  `condition` (ex. « le PJ est aveuglé », « le gobelin est terrassé à <5 PV et fuit » :
  la *fuite* est une décision du MJ, l'éventuel dégât/condition est une primitive).

### 12.4 Cas limites (résolution au moteur, usage au scénario)

| Cas | Primitive moteur | Décision d'usage (MJ) |
|---|---|---|
| **Dés de sauvegarde** (mort) | à exposer (`jet-sauvegarde`) | le MJ déclare quand le PJ tombe à 0 |
| **Réactions** (attaque d'opportunité) | `jet-monstre`/`jet-joueur` au moment voulu | le MJ décide de la déclencher |
| **Actions légendaires / repousses** | primitive dédiée (à prévoir) | le MJ décide d'en dépenser |
| **Recharge** (pouvoir 5-6 sur d6) | lancer le d6 au moteur | le MJ choisit d'employer le pouvoir |
| **Concentration** (rupture) | `condition` / `PATCH` | le MJ déclare la rupture |

> Tant qu'une primitive n'existe pas côté moteur, le MJ **ne résout pas lui-même** :
> il s'abstient ou demande l'endpoint manquant. La mécanique ne revient jamais au LLM.

### 12.5 À faire côté code (prolongement combat)

- [ ] Exposer une primitive **jet de sauvegarde** (`POST /api/combat/{id}/jet-sauvegarde`).
- [ ] Exposer les **pouvoirs multiples** d'un monstre (liste d'actions par spec,
      sélection par `action` au moment de `jet-monstre`) — aujourd'hui une seule
      action principale par spec.
- [ ] Primitives **recharge** (d6) et **action légendaire** si le périmètre l'exige.

---

## 13. Campagne / scénario — le moteur mémorise, le MJ déclare

> **Règle d'or (prolongement du combat)** : **le LLM ne génère pas l'état, il le
> déclare ; le moteur ne crée pas l'histoire, il la mémorise.** Le moteur tient la
> *structure* du scénario (lieux, PNJ, crochets, défis, blocs, phase, chronologie) ;
> le MJ en écrit la *prose* et déclare chaque événement. Le contenu narratif reste
> du texte opaque pour le moteur.

Moteur : `dnd_perso/campagne.py` · Router : `jdr_api/routers/campagne.py` ·
État : `data-campagne/campagne-<id>.json` (un fichier par campagne, relu à chaque appel).

### 13.1 Les 5 principes encodés dans la structure

| Principe | Champ(s) de la `Campagne` |
|---|---|
| Accroche & Enjeux (≥2 crochets liés à un PJ) | `accroche`, `enjeux`, `crochets[].lie_a_pj` |
| Structure par Situations (≥2 approches/défi) | `defis[].approches` |
| Équilibre des 3 Piliers | `lieux[].piliers` ⊆ {exploration, social, combat} |
| Rythme Montagne Russe (4 temps) | `phase` ∈ accroche→montee→climax→conclusion |
| Schrödinger's Dungeon (blocs réutilisables) | `blocs[]` (déplaçables via `deplacer_bloc`) |

La structure est **signalée, jamais bloquante** : `etat()` renvoie `structure_valide`
et `avertissements_structure` (ex. <2 crochets liés à un PJ, défi à 1 approche). Le MJ
peut ouvrir un scénario incomplet et le compléter.

### 13.2 Difficulté = Mode B (le moteur INFORME, le scénario DÉCIDE)

La campagne porte un `danger` (`facile`/`normale`/`mortelle`) = **choix du MJ**.
`advisory_difficulte(niveaux_pj, rencontre)` compare le budget d'XP du groupe au CR des
monstres (seuils SRD 5.2.1) et renvoie un `degre` (tres_facile→mortelle) + un `conseil`.
**Il ne modifie jamais stats ni effectifs.** La seule primitive bornée d'ajustement est
l'effectif (`nb` d'exemplaires), décidée par le MJ.

### 13.3 Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/api/campagne/ouvrir` | Ouvre une campagne depuis la structure JSON (`id` défaut horodaté). Renvoie `etat()`. |
| `POST` | `/api/campagne/importer` | Importe depuis un **Markdown à front-matter** (`{markdown, id?}`). Le corps MD est ignoré pour l'état. |
| `GET` | `/api/campagne` | Liste (`{id, titre, phase, active}`). |
| `GET` | `/api/campagne/{id}` | État complet (relecture après reset de contexte). |
| `PATCH` | `/api/campagne/{id}` | Mutation déclarée : `{action, ...}` (voir ACTIONS). |
| `POST` | `/api/campagne/{id}/advisory` | Advisory d'équilibrage (`{niveaux_pj?, monstres?/rencontre?}`). |
| `POST` | `/api/campagne/{id}/cloturer` | Clôture (rend inactive, journalise). |

**ACTIONS** (point d'entrée unique `PATCH`, `action` + paramètres) : `avancer_phase`,
`resoudre_crochet`/`ouvrir_crochet`/`abandonner_crochet` (`id`), `rencontrer_pnj`/
`decouvrir_lieu` (`nom`), `changer_attitude` (`nom`, `attitude`), `deplacer_bloc`
(`id`, `position`), `ajouter_indice` (`indice`), `accorder_recompense` (`recompense`).

### 13.4 Import Markdown (front-matter, stdlib uniquement)

Le format d'un scénario est un fichier `.md` dont le **front-matter YAML** porte la
structure (pas de JSON à la main). Parseur **stdlib only** (pas de pyyaml dans l'image) :
`campagne_depuis_markdown(texte, id_fallback)`. Le corps du Markdown reste la prose
lisible du scénario ; il n'entre pas dans l'état canonique.

### 13.5 Méthodes de l'outil OWUI (`dnd_perso_tool`)

`ouvrir_une_campagne` · `etat_de_la_campagne` · `faire_avancer_la_campagne` ·
`advisory_de_difficulte` · `clore_la_campagne`. Chacune renvoie le JSON du serveur,
`ensure_ascii=False`, sans rien recalculer côté LLM.
