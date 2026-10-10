---
id: test-mineur
titre: Le Moulin des Eaux-Noires
synopsis: "Le meunier des Eaux-Noires a disparu depuis trois nuits ; son moulin tourne encore, mais le grain qu'il moud n'est plus du grain."
pj: [Aldric, Brune]
phase: accroche
danger: normale
accroche: "Au petit matin la roue du moulin tourne à vide et l'eau du bief est noire et tiède ; la fille du meunier attend le groupe sur la berge, une empreinte de sabots de chèvre plein la main."
enjeux: "Si le moulin continue de moudre ce qui n'est pas du grain, la farine empoisonne tout le val avant la prochaine lune."
motivations: "Le val nourrit les PJ ; Aldric y a grandi, Brune y a une dette de grain impayée."
lieux:
  - nom: Le moulin
    description: "Bâtiment de pierre au bord du bief, roue qui tourne sans meunier."
    obstacles: "La trappe de la trémie est verrouillée de l'intérieur."
    piliers: [exploration, combat]
    rencontre:
      titre: Ce qui moud dans la trémie
      terrain: "Sol glissant de farine, roue qui assourdit les pas."
      monstres:
        - nom: Gobelin
          nb: 2
          cr: "1/4"
          comportement: "Attaque le PJ isolé, fuit sous 5 PV."
          pouvoirs_a_utiliser: [Avantage du terrain]
  - nom: La clairière du bosquet
    description: "Clairière où le meunier menait paître ses chèvres."
    obstacles: "Traces contradictoires, aucune piste unique."
    piliers: [exploration, social]
  - nom: Le manoir du meunier
    description: "Demeure cossue, témoin du passé du meunier."
    obstacles: "La veuve ne parle qu'en confiance."
    piliers: [social]
pnj:
  - nom: Mireille
    objectif: "Retrouver son père vivant."
    faille: "Paiera n'importe qui, ment par omission."
    attitude: méfiante
  - nom: Gaspard
    objectif: "Racheter la dette de grain du meunier."
    faille: "Cupide, bavard quand on lui offre à boire."
    attitude: neutre
defis:
  - nom: La trémie verrouillée
    approches: [Forcer la serrure, Négocier avec ce qui est enfermé, Chercher la clé]
  - nom: Savoir ce que le moulin a moulu
    approches: [Interroger Gaspard, Analyser la farine, Suivre les charrettes]
crochets:
  - id: c1
    titre: L'héritage du moulin
    lie_a_pj: Aldric
  - id: c2
    titre: La dette de grain
    lie_a_pj: Brune
blocs:
  - id: b1
    titre: La ronde des sabots
    contenu: "Une créature à sabots de chèvre suit le groupe ; réutilisable ailleurs."
    position: reserve
---

## Accroche

Le meunier des Eaux-Noires n'est pas rentré depuis trois nuits. Sa fille Mireille
attend le groupe sur la berge, une empreinte de sabots plein la main.

## Montée

Le moulin tourne à vide. Dans la trémie, quelque chose moud. Gaspard, le créancier,
sait ce que le meunier charriait la nuit — mais il faut lui soutirer.

## Climax

Ce qui moud dans la trémie n'est pas un gobelin : c'est la raison pour laquelle le
bief est noir. Le choix du groupe décide si le val est sauvé avant la lune.

## Conclusion

La farine est sauvée — ou le val la mangera. Mireille paie, ou maudit.
