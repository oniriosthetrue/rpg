---
name: test-ui
description: >-
  Méthodologie de test UI end-to-end via les outils navigateur (Playwright /
  read_page / click_element) — comment tester une interface SANS se fier aux
  apparences. USE FOR : tester une page/webapp en navigateur (formulaire, wizard,
  chat SSE, liste, CRUD) ; valider un fix frontend avant commit/déploiement ;
  vérifier qu'une UI respecte l'INTENTION utilisateur et pas seulement « ça avance
  sans crash ». MOTS-CLÉS déclencheurs : tester l'UI, tester en navigateur,
  Playwright, valider une page, smoke test UI, tester un formulaire/wizard,
  vérifier une fiche/résultat. MOTS-CLÉS anti-usage : tests unitaires/backend
  (unittest), déploiement Docker (skill mj-dnd-app), benchmark LLM. Le skill encode
  la leçon n°1 : « vérifier la SÉMANTIQUE (mes choix sont-ils conservés ?), pas le
  FLUX (est-ce que ça avance ?) », plus les pièges concrets vus sur mj-dnd
  (multi-sélection, hydratation de liste, rebuild web+api).
---

# Test UI end-to-end (navigateur / Playwright)

> Objectif : prouver qu'une interface fait ce que l'utilisateur VEUT, pas juste
> qu'elle ne plante pas. La règle d'or : **tester la sémantique, pas le flux.**

## 0. Règle d'or — sémantique > flux

Le piège n°1 (faussement validé sur mj-dnd, wizard création 2026-10-11) : tester
« est-ce que le parcours avance sans crash ? » au lieu de « est-ce que MES choix
sont respectés ? ». Un bug de multi-sélection est passé parce qu'on a cliqué UN
seul élément, vu l'étape avancer, et rationalisé.

**Avant de déclarer un test UI réussi, répondre OUI à :**
1. Ai-je saisi **plusieurs** valeurs là où plusieurs sont possibles, et **toutes**
   ressortent-elles côté résultat / persistance / API ?
2. Ai-je relu la **sortie** (fiche, JSON, réponse réseau, DB) contre ce que j'ai
   **SAISI** — pas juste contre « c'est un truc valide » ?
3. Ai-je testé l'**intention réelle** (choisir N éléments, soumettre un vrai
   formulaire), pas le cas minimal (1 clic) ?

## 1. Protocole de test (déroulé systématique)

1. **Cartographier l'intention** par écran : quelles entrées l'utilisateur saisit,
   combien, et où le résultat doit atterrir (UI, localStorage, fichier, API).
2. **Snapshot d'état initial** (`read_page`) avant toute action — point de contrôle.
3. **Saisir au-delà du cas minimal** : plusieurs éléments, valeurs limites (vide, max,
   caractères spéciaux), et surtout **plusieurs choix** sur tout champ multi.
4. **Actionner** (clic, submit, envoi SSE) puis **re-snapshot**.
5. **Relire la sortie contre la saisie** : lister ce que j'ai entré, vérifier
   élément par élément qu'il est présent. Ne pas se contenter de « la fiche est
   cohérente ».
6. **Vérifier la persistance** : recharger / rouvrir l'objet et confirmer que ça
   tient (pas juste l'état React en mémoire).
7. **Vérifier les chemins d'erreur** : soumission vide, entrée invalide, annulation.

## 2. Pièges concrets rencontrés (mj-dnd, réutilisables ailleurs)

### 2.1 Multi-sélection : 1 clic ≠ 1 envoi
- **Symptôme** : sur une étape « choisis plusieurs » (compétences, sorts), un SEUL
  clic fait avancer l'étape. **C'est un signal d'alarme, jamais un comportement normal.**
- **Cause** : chaque clic envoie une réponse séparée → le backend n'en voit qu'une,
  tire le reste au hasard et passe à l'étape suivante.
- **Correctif UI** : accumuler une sélection locale (toggle `selection: string[]`),
  envoyer groupé d'un coup (ex. `repondre(selection.join(", "))` derrière un bouton
  « Valider (n) »). Le moteur attend TOUTES les options en UNE réponse.
- **Test qui l'aurait attrapé** : cliquer 3 sorts, vérifier que les 3 (et eux seuls)
  sont sur la fiche finale.

### 2.2 Rationalisation = ennemie
- Si un comportement semble bizarre (étape qui avance trop vite, un seul élément
  retenu, valeur « par défaut » suspecte), **le creuser**, ne pas inventer
  d'explication rassurante (« le moteur complète au hasard, c'est normal »).
- Les données « étranges » sur la sortie (6 sorts aléatoires alors que j'en ai
  choisi 1) ÉTAIENT la preuve du bug.

### 2.3 Hydratation de liste / async
- Une liste peut mettre ~1 instant à s'hydrater après un reload ou une mutation.
  **Re-snapshot avant de conclure à un bug** (liste vide ≠ liste cassée).
- Pour le SSE (chat) : attendre la fin du stream (`fin`/`erreur`) avant de lire,
  sinon on snapshot un état partiel.

### 2.4 Frontend ET backend déployés
- Un fix touchant les deux doit être **rebuild des deux images** avant test en
  navigateur, sinon on teste une UI neuve contre une API obsolète (faux bugs /
  faux verts). Cf. skill `mj-dnd-app` : `docker compose build web api && up -d`.
- En cas de doute, vérifier les routes réellement servies (openapi) plutôt que
  de croire le source.

## 3. Checklist avant de dire « UI testée / OK »

- [ ] Chaque champ multi-choix testé avec **≥2 valeurs**, toutes retrouvées à la sortie.
- [ ] Sortie relue **contre la saisie** (pas juste « valide »).
- [ ] Persistance vérifiée (reload / réouverture).
- [ ] Chemins d'erreur testés (vide, invalide, annulation, stop SSE).
- [ ] Images déployées = dernier code (si test en conditions réelles).
- [ ] Aucun symptôme « bizarre » rationalisé — tous creusés.

## 4. Outils navigateur — usage

- `read_page` > screenshot pour agir (donne les refs cliquables).
- `click_element` / `type_in_page` avec `ref` issus du snapshot.
- Pour un wizard/flow : refaire un `read_page` **après chaque action** (l'état change).
- Ne jamais conclure sur un seul snapshot : avant → action → après.

## 5. Anti-patterns

- ❌ Valider un parcours en cliquant le cas minimal (1 élément, 1 étape).
- ❌ Vérifier la cohérence interne d'une sortie sans la comparer à la saisie.
- ❌ Conclure « bug » sur une liste vide sans re-snapshot (hydratation).
- ❌ Tester une UI reconstruite contre une API non rebuildée.
- ❌ Accepter un comportement surprenant sans l'explorer.
