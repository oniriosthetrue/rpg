# Architecture — Jeu de rôle D&D 5e dans Open WebUI

> Projet : `/home/linus/qwen_3.8_vnimanieAI` · Service : `open-webui` (`rpg.minervia.fr`)
> Décisions validées : **règles strictes (tool calling fort)** · **strictement SRD (RAG strict)** ·
> **solo ET multi-joueurs** · **nouvelle arborescence complète** · **objets magiques extraits du SRD**.

---

## 1. Principe directeur

Un vrai JDR a **deux cerveaux distincts**, et c'est là que tout se joue :

| | Cerveau **narratif** | Cerveau **règles** |
|---|---|---|
| Contenu | descriptions, dialogues, ambiance, intentions | chiffres, jets, tables, statistiques |
| Support | le **modèle** (créativité) | les **outils** + le **RAG** (déterminisme) |
| Interdiction | inventer une règle / un monstre | broder du lore hors corpus |

Règle d'or de conception : **le LLM ne calcule jamais rien.** Il *demande* une action
(`roller_un_d20`), il *lit* une fiche (`lookup_monstre`), et il *raconte* le résultat.
Tout ce qui est chiffré (dés, PV, initiative, conditions, inventaire) vient d'un outil
qui renvoie du JSON. Tout ce qui est factuel (sort, objet, monstre, lore) vient du RAG.
Le modèle n'a **aucune** autorité pour combler un trou : s'il ne trouve pas, il le dit.

```mermaid
flowchart LR
    A[Joueur: "j'attaque le gobelin"] --> B[MJ OWUI]
    B -->|besoin de faits| C[Knowledge SRD<br/>RAG + métadonnées]
    B -->|besoin de calcul| D[Tools<br/>des / combat / inventaire]
    C -->|fiche + source| B
    D -->|JSON: jet, PV, état| B
    B -->|récit| A
```

---

## 2. Les 10 aspects d'un JDR → capacités Open WebUI

| # | Aspect du JDR | Capacité OWUI | Rôle précis |
|---|---|---|---|
| 1 | **Création de personnage** | `Prompts` (commande `/nouveau-perso`) + `Tools` (génération de stats, tables de races) | Le prompt pilote un tunnel de création guidé ; les tables (race, antécédent, traits) viennent du corpus. |
| 2 | **Exploration / narration** | `Models` (prompt système MJ) + `Knowledge` (lieux, PNJ) + `Web search` | Décrire, jouer les PNJ, réagir. Le web search est **désactivé par défaut** (voir §4). |
| 3 | **Combat** | `Tools` (fonctions Python : initiative, attaque, dégâts, conditions) | C'est le cœur du tool calling. Le MJ ne lance **jamais** un dé lui-même. |
| 4 | **Magie / sorts** | `Knowledge` (corpus sorts) + `Tools` (emplacement de sort, durée, concentration) | Fiche de sort exacte via RAG ; gestion des emplacements via outil d'état. |
| 5 | **Objets magiques** | `Knowledge` (corpus objets, **à générer**) + `Tools` (inventaire, poids, prix) | À extraire du PDF : c'est le trou béant actuel. |
| 6 | **Lore / univers** | `Knowledge` (corpus lore) + `RAG_TEMPLATE` imposant la citation | Le MJ cite sa source ; interdiction d'inventer un nom propre. |
| 7 | **Tables aléatoires** | `Tools` (d100 aléatoire, tables de rencontre / butin / météo) | Table = fichier JSON en données, pas dans le prompt. |
| 8 | **Gestion de campagne** | `Notes` (fiche PJ partagée, état du monde) + `Tools` (sauver/charger) + `Tags` | L'état du monde est **externe au chat** : sinon il se perd au premier reset. |
| 9 | **Multi-joueurs** | `Channels` + `Notes` partagées + `Groups` + `DEFAULT_GROUP_SHARE_PERMISSION` | Un canal = la table de jeu. Une note = la fiche de groupe. |
| 10 | **Récap / journal** | `Prompts` (`/recap`) + `Memories` (préférences joueur) + export | Récap de fin de séance, fils rouges, quêtes ouvertes. |

Trois capacités transversales :

| Capacité OWUI | Usage JDR |
|---|---|
| **Citations / références** | Chaque affirmation de règle est traçable vers la fiche SRD. Anti-hallucine. |
| **Eval / evaluations** | Tests de non-régression : le MJ doit refuser ce qui n'est pas dans le SRD. |
| **MCP (`ENABLE_MCP_SERVER_CONNECTION`)** | Optionnel : un serveur de règles D&D externe si les tools deviennent gros. |

---

## 3. Corpus de connaissances (le RAG)

### 3.1 Arborescence cible — nouvelle, tout restructurer

```
dnd/
├─ FR_SRD_CC_v5.2.1.pdf              # SOURCE UNIQUE DE VÉRITÉ (380 p., 2 colonnes)
└─ srd-5.2.1/                        # ← NOUVEAU : corpus structuré, prêt pour OWUI
   ├─ 00-index/
   │  └─ index.md                    # table des matières + conventions + mots-clés
   ├─ 01-chapitres/                  # règles générales (chap. 1-9 du SRD)
   │  ├─ 01-qu-est-ce-que-jeu.md
   │  ├─ 02-creer-un-personnage.md
   │  ├─ 03-race.md
   │  ├─ 04-classe.md
   │  ├─ 05-antecedent.md
   │  ├─ 06-alignement-linguage.md
   │  ├─ 07-equipement.md
   │  ├─ 08-regles-de-combat.md
   │  ├─ 09-entre-deux-combats.md
   │  └─ 10-conditions-etablis.md
   ├─ 02-sorts/                      # ← À GÉNÉRER (absent aujourd'hui)
   │  ├─ 00-index.md
   │  └─ <nom-du-sort>.md            # 1 fichier par sort, ~309
   ├─ 03-objets-magiques/            # ← À GÉNÉRER (absent aujourd'hui)
   │  ├─ 00-index.md
   │  └─ <nom-objet>.md              # 1 fichier par objet
   ├─ 04-monstres/                   # ← DÉPLACÉ depuis DD/srd-5.2.1-md/monstres/
   │  └─ <nom-monstre>.md            # 304 fiches, 0 incomplète
   ├─ 05-lore/                       # ← À GÉNÉRER (plans, divinités, plans d'existence)
   │  └─ *.md
   ├─ 06-tables-aleatoires/          # ← À GÉNÉRER (d100 : rencontres, butin, PNJ, météo)
   │  └─ <table>.md
   └─ 07-appendices/
      ├─ A-divinites.md
      ├─ B-lexique.md
      └─ C-planes-of-existence.md
```

> **Migration** : `dnd/DD/srd-5.2.1-md/monstres/` → `dnd/srd-5.2.1/04-monstres/`
> (le chemin `DD/` est un résidu historique, il disparaît).

### 3.2 Format d'une fiche (inchangé, validé)

Chaque fichier `.md` commence par un **en-tête de métadonnées** — c'est ce qui rend le
RAG *filtrable* et le MJ *honnête* :

```markdown
<<<FICHE>>>
id: monstres/aboleth
nom: Aboleth
type: monstre
edition: SRD 5.2.1
mots_cles: aboleth, aberration, aquatique, telepathie
niveau: 10
source: FR_SRD_CC_v5.2.1.pdf p.274
<<<CONTENU>>>

## Aboleth
Aberration de taille G, Loyale Mauvaise
...
```

- `<<<FICHE>>>` / `<<<CONTENU>>>` : délimiteurs. Le chunker OWUI coupe sur `## `, la
  fiche reste donc **un chunk = une fiche** (pas de coupe au milieu d'un bloc de stats).
- `mots_cles` : **c'est la clé du RAG FR.**
  Le joueur dit « le gros poisson télépathe », l'index sémantique + les mots-clés
  retrouvent `aboleth`. Pas de dictionnaire à maintenir.
- `source: ... p.NNN` : permet la **citation** et interdit l'invention.

### 3.3 Configuration OWUI du RAG

À reporter dans **Settings → Documents** (et non dans le prompt) :

| Clé | Valeur | Pourquoi |
|---|---|---|
| `RAG_EMBEDDING_ENGINE` | `openai` | déjà en place |
| `RAG_EMBEDDING_MODEL` | `${EMBED_MODEL_NAME}` (Qwen3-Embedding-0.6B) | déjà en place |
| `RAG_OPENAI_API_BASE_URL` | `http://embedding:8080/v1` | **sans** `/embeddings` |
| `RAG_EMBEDDING_BATCH_SIZE` | `8` | mesuré optimal sur cet hôte |
| `AIOHTTP_CLIENT_TIMEOUT` | `900` | embedding CPU lent sur les gros fichiers |
| `RAG_TOP_K` | `4`–`6` | fiches compactes : trop de contexte dilue le MJ |
| `ENABLE_RERANKER` | `False` | déjà en place (le reranker croque le temps) |
| `RAG_SYSTEM_CONTEXT` | `False` | ne pas noyer le prompt MJ |
| `RAG_SOURCE_METADATA_KEYS` | `id,nom,type,edition,mots_cles,source` | **à activer** : rend les métadonnées visibles |
| `ENABLE_CITATIONS` | `True` | exigence « strictement SRD » |

**Piège connu** : un gros fichier (570 Ko ≈ 640 chunks) fait dépasser le timeout OWUI et
la page redevient vide → **toujours uploader des fichiers par domaine** (sorts, monstres,
objets séparés), jamais un `monstres-A-Z.md` monolithique.

### 3.4 Conventions d'upload OWUI

- **Une collection OWUI par domaine** : `dnd-srd-sorts`, `dnd-srd-monstres`,
  `dnd-srd-objets`, `dnd-srd-lore`, `dnd-srd-tables`.
- **Un fichier par fiche** (pas de fichier géant) : chunking propre, citation fiable.
- **`index.md` par domaine** : liste des noms exacts + alias FR. C'est le « sommaire »
  qui permet au MJ de reformuler une question vague.
- **Upload binaire `.md` uniquement** : pas de PDF dans OWUI (le PDF est la source,
  le MD est le corpus).

---

## 4. Les outils (tool calling) — le moteur de règles

### 4.1 Emplacement

```
config/openwebui/
├─ prompts/
│  ├─ mj-systeme.md            # le MJ (prompt système global)
│  ├─ nouveau-perso.md
│  ├─ recap-de-seance.md
│  ├─ initier-combat.md
│  └─ repos-long.md
├─ tools/
│  ├─ jets_de_des.py
│  ├─ gestion_combat.py
│  ├─ inventaire.py
│  ├─ tirage_aleatoire.py
│  └─ corpus_srd.py
└─ filters/
   └─ mj_contexte.py            # middleware : état de campagne + garde-fous
```

> ⚠️ `config/dify/` est un **résidu** (prompt pour Dify, abandonné). Le nouveau corpus
> vit sous `config/openwebui/` et `dnd/srd-5.2.1/`.

### 4.2 Inventaire des tools

| Tool | Signature | Retourne | Pourquoi un tool |
|---|---|---|---|
| `roller_des` | `roller_des(nb: int, faces: int, modificateur: int = 0, avantage: int = 0, raison: str = "")` | `{jets: [...], total, succes, critique}` | **Le LLM ne sait pas lancer un dé.** C'est LE tool critique. |
| `gerer_combat` | `gerer_combat(action: str, combat_id: str, cible: str = "", params: dict = {})` | `{initiative: [...], tour, pv, conditions, resultat}` | Initiative, ordre de tour, PV, conditions, réactions. |
| `gerer_inventaire` | `gerer_inventaire(action: str, pj: str, objet: str = "", quantite: int = 1)` | `{lignes: [...], poids, or, encombrement}` | L'inventaire est un **état**, pas un souvenir du LLM. |
| `tirer_sur_table` | `tirer_sur_table(table: str, d: int = 100)` | `{ligne, valeur, description}` | Tables aléatoires (rencontres, butin, météo, PNJ). |
| `consulter_srd` | `consulter_srd(recherche: str, domaine: str = "auto")` | `{fiches: [{id, nom, contenu, source}]}` | **Filet de sécurité** quand le RAG ne suffit pas. |

### 4.3 Le contrat du MJ (à mettre dans le prompt système)

C'est ce qui rend « règles strictes » exécutable :

1. **Tout jet passe par `roller_des`.** Le MJ n'écrit jamais un chiffre de dé de sa propre
   initiative, et n'annonce jamais un résultat qu'il n'a pas reçu de l'outil.
2. **Toute donnée factuelle passe par le RAG** (ou `consulter_srd`). Le MJ ne décrit un
   sort, un objet ou un monstre qu'à partir de la fiche retournée, et cite `source:`.
3. **Interdiction d'inventer** : si aucune fiche n'est retournée, le MJ le dit
   (« hors SRD ») et propose l'alternative la plus proche **en le signalant**.
4. **Le MJ ne décide pas à la place du joueur** : il décrit la situation, demande
   l'intention, puis applique la règle.
5. **Format de sortie imposé** : `🎲 Jet : 1d20+5 = [14]+5 = 19 → Réussite (CA 15)`.
   Le joueur doit pouvoir auditer chaque ligne.
6. **En combat** : le MJ appelle `gerer_combat` à chaque étape (initiative → attaque →
   dégâts → conditions) et ne jamais « accélérer » en improvisant.

### 4.4 Pourquoi pas « tout dans le prompt »

Un prompt de 300 lignes de tables de races + 309 sorts :
- sature la fenêtre (98 304 tokens, mais le préfixe de raisonnement de Qwen3 le consomme) ;
- rend le modèle **créatif sur les chiffres** → il invente des bonus ;
- empêche l'audit (le joueur ne peut pas vérifier un jet).

Le RAG + tools garde le prompt **court** (~60 lignes de contrat) et délègue tout le reste.

---

## 5. Multi-joueurs

| Besoin | Mécanisme OWUI |
|---|---|
| Table de jeu partagée | **`Channels`** : un canal = une campagne. Les joueurs y échangent, le MJ y répond. |
| Fiche de groupe | **`Notes`** partagées : une note par PJ + une note « état du monde ». |
| Qui a parlé ? | Préfixe d'identité : le MJ nomme le PJ (`Thalia : ...`). `ENABLE_FORWARD_USER_INFO_HEADERS=True` si besoin d'identité OWUI. |
| Secrets du MJ | Le MJ ne révèle **jamais** une fiche de monstre non encore découverte → le RAG renvoie, le MJ filtre. |
| Accès | `ENABLE_SIGNUP=False` (déjà) + comptes créés par l'admin. `DEFAULT_GROUP_SHARE_PERMISSION=members`. |
| Conflits d'état | Un seul chat = une campagne. **Ne pas** multiplier les chats d'une même campagne. |

**Limite honnête** : OWUI n'est pas un VTT. Pas de carte, pas de tokens, pas de
partage d'écran de plateau. Pour ça, garder `sillytavern` ou un VTT externe.

---

## 6. Ce qu'OWUI ne fait pas (et ne faut pas lui demander)

| Limite | Conséquence | Mitigation |
|---|---|---|
| Pas de moteur de règles | Le MJ ne peut pas « vérifier » une règle hors corpus | `consulter_srd` + refus explicite |
| Pas de plateau / grille | Pas de portée en cases, pas de couvrance | Décrire en pieds / « à portée », ou VTT externe |
| Pas de persistance de partie native | Un reset de chat = perte de la partie | `gerer_inventaire` + note « état du monde » + `gerer_combat` persistant |
| RAG = retrieval, pas compréhension | Une question transversale (« comment fonctionne la furtivité ? ») peut rater | `index.md` par domaine + reformulation de la question |
| `reasoning-parser=qwen3` | Le préambule de raisonnement consomme la fenêtre | `max_tokens` explicite, ne pas sur-charger le RAG |

---

## 7. Plan de travail

### Phase 0 — Sauvegarde (obligatoire)
- [ ] `docker compose stop open-webui` puis sauvegarde du volume `open-webui-data`
      (données OWUI : chats, prompts, tools, knowledge).
- [ ] Sauvegarder `dnd/FR_SRD_CC_v5.2.1.pdf` (source unique, irremplaçable).

### Phase 1 — Corpus
- [ ] Créer `dnd/srd-5.2.1/` (arborescence §3.1).
- [ ] Déplacer `dnd/DD/srd-5.2.1-md/monstres/` → `04-monstres/` (304 fiches, validées).
- [ ] Générer `02-sorts/` depuis le PDF (extension de `scripts/srd_monstres_to_fiches.py` :
      parser de sorts, `## Nom`, bloc `Enchantement 1 action`, portée/durée/composantes).
- [ ] Générer `03-objets-magiques/` depuis le PDF (tableaux 2 colonnes, prix, poids,
      emplacements — **le gros morceau manquant**).
- [ ] Générer `05-lore/`, `06-tables-aleatoires/`, `07-appendices/`.
- [ ] Générer `00-index/index.md` (noms exacts + alias FR).
- [ ] `scripts/check_corpus.py` : chaque fiche a `id`/`nom`/`type`/`source`, 0 fiche vide.

### Phase 2 — Moteur
- [ ] Écrire `config/openwebui/tools/*.py` (5 tools, §4.2).
- [ ] Écrire `config/openwebui/prompts/mj-systeme.md` (contrat §4.3).
- [ ] Écrire `config/openwebui/filters/mj_contexte.py` (injection d'état + garde-fous).
- [ ] Tests : une scène de combat complète, une question hors-SRD (doit refuser).

### Phase 3 — Intégration OWUI
- [ ] Uploader les 5 collections de connaissances.
- [ ] Déclarer le **modèle custom MJ** (modèle vLLM + prompt MJ + tools + knowledge).
- [ ] Activer `ENABLE_CITATIONS`, `RAG_SOURCE_METADATA_KEYS`.
- [ ] Configurer `Channels` (une table par campagne).

### Phase 4 — Recette
- [ ] 10 tests de non-régression (création, combat, sort, objet, lore, refus hors-SRD).
- [ ] Ajuster `RAG_TOP_K` et le prompt selon les ratés.

### Phase 5 — Dépendances à trancher
- [ ] `config/dify/` : supprimer ou documenter (résidu).
- [ ] `sillytavern` : conserver (VTT) ou retirer.

---

## 8. Risques identifiés

| Risque | Impact | Parade |
|---|---|---|
| PDF → sorts mal parsé (2 colonnes, en-têtes/pieds) | fiches tronquées | `COL_SPLIT_X=300`, filtre `y>730`, `TYPE_RE` avec « taille M ou P », skip « Changement d'aspect » |
| Corpus trop gros pour l'embedding CPU | upload qui time-out, page vide | fichiers par domaine, `BATCH_SIZE=8`, `AIOHTTP_CLIENT_TIMEOUT=900` |
| Le MJ invente un monstre | triche invisible | `mots_cles` + refus explicite + citation `source:` |
| Le MJ « lance » un dé tout seul | triche massive | `roller_des` obligatoire, format de sortie imposé |
| Le LLM ignore le tool call | retour en mode conteur | `--enable-auto-tool-choice` (déjà) + contrat explicite + eval |
| Fenêtre de contexte consommée par le raisonnement | réponses coupées | `max_tokens`, RAG minimal, pas de `RAG_FULL_CONTEXT` |
| Multi-joueurs : le MJ parle pour les PJ | écrase les joueurs | contrat §4.3 + `Channels` |

---

## 9. Fichiers de référence

| Fichier | Rôle |
|---|---|
| `dnd/FR_SRD_CC_v5.2.1.pdf` | source unique du corpus |
| `dnd/DD/srd-5.2.1-md/monstres/` | 304 fiches validées (à déplacer) |
| `scripts/srd_monstres_to_fiches.py` | PDF → fiches (à étendre : sorts, objets) |
| `scripts/srd_md_to_lorebook.py` | MD → lorebook ST (réutilisable pour l'index OWUI) |
| `.github/skills/extraction-pdf/SKILL.md` | procédure PDF (pièges documentés) |
| `config/dify/assistant-c2s-prompt-v2.md` | gabarit de prompt strict-corpus |
| `docker-compose.yml` L190-243 | service `open-webui` (config OWUI) |
