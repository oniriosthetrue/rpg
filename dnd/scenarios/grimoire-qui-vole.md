---
id: grimoire-qui-vole
titre: Le Grimoire qui avait des Ailes
synopsis: "Le soir de sa première étoile filante, le jeune magicien a réveillé son grimoire : le voilà qui vole dans la Forêt Murmure avec son sortilège préféré encore dedans."
pj: [Léo]
phase: accroche
danger: facile
accroche: "À minuit, une étoile filante entre par la fenêtre de la tour et se pose sur le vieux grimoire de grand-mère. Le livre bâille, déploie deux pages comme des ailes, et s'envole par la fenêtre en emportant le sortilège que Léo préfère."
enjeux: "Si le grimoire ne revient pas avant le lever du soleil, ses pages se tremperont de rosée et le sortilège préféré de Léo disparaîtra pour toujours."
motivations: "Le grimoire est le plus beau cadeau de grand-mère ; et c'est Léo qui, sans le vouloir, lui a donné vie."
lieux:
  - nom: La tour de Léo
    description: "Petite chambre de magicien en herbe, pleine d'étoiles qui clignotent au plafond et d'une fenêtre grande ouverte sur la nuit."
    obstacles: "Le grimoire est déjà loin ; il ne reste que des petites empreintes d'encre scintillante sur le rebord."
    piliers: [exploration]
  - nom: Le Pont-Chantant
    description: "Un vieux pont de pierre qui grince une mélodie quand on le traverse, au-dessus d'un ruisseau qui rit tout seul."
    obstacles: "Gribouille le troll bloque le pont et n'aime pas qu'on passe sans lui parler."
    piliers: [social]
  - nom: La Clairière Endormie
    description: "Une clairière douce où l'herbe brille doucement ; le grimoire s'y est posé sur une souche, un peu essoufflé."
    obstacles: "Le grimoire est gardé par un tout petit dragon de papier qui joue avec les étoiles tombées."
    piliers: [exploration, social, combat]
    rencontre:
      titre: Le Petit Dragon de Papier
      terrain: "Herbe molle et étoiles filantes au sol qui glissent sous les pieds."
      monstres:
        - nom: Petit Dragon de Papier
          nb: 1
          cr: "0"
          comportement: "Il joue et chatouille, il ne fait jamais vraiment mal. Il s'envole si on le poursuit, et il se pose tout doux si on lui chante une comptine."
          pouvoirs_a_utiliser: [Envol de papier, Chatouilles d'encre]
pnj:
  - nom: Filament
    objectif: "Retrouver l'étoile filante dont il s'occupe, celle qui s'est posée sur le grimoire."
    faille: "Il est très fier : il aide volontiers dès qu'on le félicite ou qu'on lui demande poliment."
    attitude: joueur
  - nom: Gribouille
    objectif: "Ne plus être seul sur son pont et avoir un ami avec qui rire."
    faille: "Il adore les devinettes, les chatouilles et les bonbons ; il fond dès qu'on est gentil avec lui."
    attitude: grognon mais seul
defis:
  - nom: Traverser le Pont-Chantant
    approches: [Résoudre la devinette de Gribouille, Lui offrir un bonbon ou une chatouille, Le faire rire avec un petit sort rigolo]
  - nom: Rattraper le grimoire qui vole
    approches: [Le charmer en lui chantant la comptine de grand-mère, Demander à Filament de l'éclairer pour le voir, Le suivre à pied grâce aux empreintes d'encre]
crochets:
  - id: c1
    titre: Le cadeau de grand-mère
    lie_a_pj: Léo
  - id: c2
    titre: Le sortilège qui a tout réveillé
    lie_a_pj: Léo
blocs:
  - id: b1
    titre: La pluie d'étoiles filantes
    contenu: "Une pluie d'étoiles filantes peut tomber n'importe où dans la forêt pour éclairer la route ou cacher Léo. Le MJ la fait apparaître au moment le plus utile."
    position: reserve
---

## Accroche (5 min)

C'est la nuit de la première étoile filante de Léo, son grand soir de magicien. Une
étoile entre par la fenêtre et se pose sur le vieux grimoire de grand-mère. Le livre
bâille, déploie deux pages comme des ailes, et s'envole dans la nuit en emportant le
sortilège que Léo préfère au monde. Il ne reste que des empreintes d'encre qui brillent.

> Astuce MJ : laisse l'enfant décrire sa tour, son sortilège préféré et ce qu'il fait
> en premier. Suis-le, ne le force pas.

## Montée (20-25 min)

Léo suit les empreintes d'encre dans la Forêt Murmure. **Filament**, un petit feu follet
très fier, accepte de l'éclairer s'il lui demande gentiment. Sur le **Pont-Chantant**,
**Gribouille** le troll grogne : il ne laissera passer que s'il rit, s'il joue aux
devinettes ou s'il reçoit un bonbon. Rien de méchant — Gribouille veut surtout un ami.

> Astuce MJ : s'il bloque, fais intervenir Filament ou une pluie d'étoiles (bloc b1).
> Il n'y a pas de mauvaise réponse : félicite chaque idée imaginative.

## Climax (15 min)

Dans la **Clairière Endormie**, le grimoire s'est posé sur une souche. Un **tout petit
dragon de papier** joue avec les étoiles tombées et garde le livre. Il ne fait pas de
vrai mal : il chatouille et s'envole. Pour le calmer, Léo peut lui chanter la comptine
de grand-mère, lui montrer un sortilège rigolo, ou simplement jouer avec lui.

> Astuce MJ : ce « combat » est une partie de jeu, pas une bagarre. Le dragon se rend
> dès que Léo est gentil ou malin. Décris des chatouilles, pas des blessures.

## Conclusion (5 min)

Le petit dragon s'endort sur l'épaule de Léo, le grimoire referme ses ailes et le
sortilège préféré brille de nouveau. De retour à la tour, Léo a gagné un ami de papier
et une étoile filante à garder dans sa poche.

> Récompenses à déclarer : un ami (le Petit Dragon de Papier), une étoile filante,
> et le grimoire retrouvé.
