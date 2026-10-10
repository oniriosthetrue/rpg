"""Panneau « fiche de personnage » pour le joueur — page HTML autonome.

Sert une page qui affiche en continu la fiche d'un personnage et se
réactualise seule. Pensée pour être ouverte dans une seconde fenêtre à côté
d'Open WebUI (MJ D&D).

Chemin public (via Traefik, lecture seule) :
    https://api.minervia.fr/jdr/panel?p=<nom_du_personnage>

La page appelle `/jdr/api/personnages` et `/jdr/api/personnages/<nom>` sur la
MÊME origine : la clé X-API-Key est injectée par Traefik, jamais par le
navigateur. Cette route ne renvoie que du HTML statique (aucune donnée), donc
elle n'exige pas de clé elle-même.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from dnd_perso import extract

router = APIRouter()

# HTML + JS autonomes (aucune dépendance externe, rendu markdown minimal).
# L'API est relative ("api/...") pour rester sous le préfixe /jdr/ tel que servi.
_PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fiche de personnage</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
    background: #1a1b26; color: #d5d7e0;
  }
  header {
    position: sticky; top: 0; z-index: 2;
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    padding: 10px 14px; background: #16171f; border-bottom: 1px solid #2a2c3a;
  }
  header h1 { font-size: 15px; margin: 0; font-weight: 600; color: #e7e9f0; }
  select, button {
    font: inherit; background: #23242f; color: #d5d7e0;
    border: 1px solid #3a3c4d; border-radius: 7px; padding: 5px 9px; cursor: pointer;
  }
  button:hover, select:hover { border-color: #5b6078; }
  #statut { font-size: 12px; color: #8b8fa3; margin-left: auto; }
  main { padding: 14px 16px 40px; max-width: 820px; margin: 0 auto; }
  .vide { color: #8b8fa3; font-style: italic; }
  .erreur { color: #e0717a; }

  /* Identité */
  .id { margin: 4px 0 14px; }
  .id-nom { font-size: 22px; font-weight: 700; color: #eef0f7; line-height: 1.1; }
  .id-sub { font-size: 13px; color: #9aa0b4; margin-top: 2px; }

  /* Statistiques clés */
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 16px; }
  .stat { background: #20212c; border: 1px solid #2a2c3a; border-radius: 10px;
          padding: 10px 6px; text-align: center; }
  .stat .v { font-size: 20px; font-weight: 700; color: #eef0f7; }
  .stat .l { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #8b8fa3; }

  section { margin: 16px 0; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: #8b8fa3;
       margin: 0 0 8px; border-bottom: 1px solid #2a2c3a; padding-bottom: 4px; }

  /* Caractéristiques */
  .carac { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
  .cc { background: #20212c; border: 1px solid #2a2c3a; border-radius: 10px;
        padding: 8px 4px; text-align: center; }
  .cc-l { font-size: 11px; color: #8b8fa3; }
  .cc-v { font-size: 20px; font-weight: 700; color: #eef0f7; line-height: 1.1; }
  .cc-m { font-size: 13px; color: #7aa2f7; font-weight: 600; }

  /* Jets de sauvegarde */
  .jets { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
  .jet { background: #1e1f29; border: 1px solid #2a2c3a; border-radius: 8px;
         padding: 6px 4px; text-align: center; }
  .jet .l { font-size: 11px; color: #8b8fa3; }
  .jet .v { font-size: 14px; font-weight: 600; color: #c0caf5; }

  /* Compétences */
  .comps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 2px 16px; }
  .comp { display: flex; justify-content: space-between; font-size: 13px;
          padding: 3px 6px; border-radius: 6px; }
  .comp b { color: #9aa0b4; font-weight: 600; }
  .comp.mait { background: #232838; }
  .comp.mait span::before { content: '\\25CF  '; color: #7aa2f7; }
  .comp.mait b { color: #7aa2f7; }

  /* Puces (langues, sorts) */
  .puces { display: flex; flex-wrap: wrap; gap: 6px; }
  .puce { background: #23242f; border: 1px solid #3a3c4d; border-radius: 999px;
          padding: 3px 10px; font-size: 12px; }

  /* Liste simple (équipement) */
  .liste { margin: 0; padding-left: 18px; }
  .liste li { margin: 2px 0; }

  .pied { margin-top: 18px; font-size: 11px; color: #6b6f82; text-align: center; }

  /* Infobulles (survol + tap) */
  .info { position: relative; cursor: help; }
  .info::after {
    content: attr(data-info);
    position: absolute; left: 50%; bottom: calc(100% + 8px); transform: translateX(-50%);
    z-index: 20; width: max-content; max-width: min(360px, 90vw);
    max-height: 60vh; overflow: auto;
    background: #0f1017; color: #dfe2ee; border: 1px solid #3a3c4d; border-radius: 8px;
    padding: 9px 12px; font-size: 13px; line-height: 1.5; font-weight: 400;
    text-align: left; white-space: normal; box-shadow: 0 6px 20px rgba(0,0,0,.5);
    opacity: 0; visibility: hidden; pointer-events: none;
    transition: opacity .12s ease;
  }
  .info::before {
    content: ''; position: absolute; left: 50%; bottom: calc(100% + 2px);
    transform: translateX(-50%); z-index: 21;
    border: 6px solid transparent; border-top-color: #3a3c4d;
    opacity: 0; visibility: hidden; transition: opacity .12s ease;
  }
  .info:hover::after, .info:hover::before,
  .info.show::after, .info.show::before { opacity: 1; visibility: visible; }
  /* Sans description : pas de curseur aide ni de bulle vide */
  .info.noinfo { cursor: default; }
  .info.noinfo::after, .info.noinfo::before { display: none; }

  /* Responsive : on resserre les grilles sur petit écran */
  @media (max-width: 560px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
    .carac { grid-template-columns: repeat(3, 1fr); }
    .jets  { grid-template-columns: repeat(3, 1fr); }
    .comps { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<header>
  <h1>Fiche de personnage</h1>
  <select id="perso" title="Choisir le personnage"></select>
  <button id="refresh" title="Actualiser maintenant">&#8635;</button>
  <span id="statut"></span>
</header>
<main id="fiche"><p class="vide">Chargement…</p></main>
<script>
(function () {
  var REFRESH_MS = 5000;
  var select = document.getElementById('perso');
  var fiche = document.getElementById('fiche');
  var statut = document.getElementById('statut');
  var timer = null;
  var lastKey = null;

  function setStatut(t) { statut.textContent = t; }

  // Descriptions des sorts/compétences (infobulles), chargées une fois puis en cache.
  var INFOS = null;
  function chargerInfos() {
    if (INFOS) return Promise.resolve(INFOS);
    return fetch('api/infos', { headers: { 'Accept': 'application/json' }, cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) { INFOS = d || {}; return INFOS; })
      .catch(function () { INFOS = { sorts: {}, competences: {} }; return INFOS; });
  }
  // Ajoute une infobulle (attribut data-info) à un élément si on a une description.
  function info(el, texte) {
    if (texte) { el.setAttribute('data-info', texte); el.classList.add('info'); }
    else { el.classList.add('info', 'noinfo'); }
  }
  // Applique les infobulles sur les sorts (.puce) et compétences (.comp span) rendus.
  function appliquerInfos() {
    chargerInfos().then(function (infos) {
      var sorts = (infos && infos.sorts) || {};
      var comps = (infos && infos.competences) || {};
      fiche.querySelectorAll('.puce[data-nom]').forEach(function (el) {
        info(el, sorts[el.getAttribute('data-nom')]);
      });
      fiche.querySelectorAll('.comp span[data-nom]').forEach(function (el) {
        info(el, comps[el.getAttribute('data-nom')]);
      });
    });
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function signed(n) { n = Number(n) || 0; return (n >= 0 ? '+' : '') + n; }

  // Rendu structuré en tableaux/grilles à partir du JSON du personnage.
  function renduFiche(p) {
    if (!p) return '<p class="erreur">Données de personnage absentes.</p>';
    var h = '';

    // Identité
    h += '<div class="id"><div class="id-nom">' + esc(p.nom) + '</div>' +
         '<div class="id-sub">' + esc([p.espece, p.classe, p.historique].filter(Boolean).join(' · ')) +
         (p.alignement ? ' · ' + esc(p.alignement) : '') + '</div></div>';

    // Statistiques clés
    var stats = [
      ['Niveau', p.niveau], ['PV', p.pv], ['CA', p.ca],
      ['Init.', signed(p.initiative)], ['Maîtrise', signed(p.bonus_maitrise)],
      ['XP', p.xp]
    ];
    h += '<div class="stats">' + stats.map(function (s) {
      return '<div class="stat"><div class="v">' + esc(s[1]) + '</div><div class="l">' + esc(s[0]) + '</div></div>';
    }).join('') + '</div>';

    // Caractéristiques
    var carac = p.carac || {}, mods = p.mods || {};
    h += '<section><h2>Caractéristiques</h2><div class="carac">' +
      Object.keys(carac).map(function (k) {
        return '<div class="cc"><div class="cc-l">' + esc(k.slice(0, 3)) + '</div>' +
               '<div class="cc-v">' + esc(carac[k]) + '</div>' +
               '<div class="cc-m">' + esc(signed(mods[k])) + '</div></div>';
      }).join('') + '</div></section>';

    // Jets de sauvegarde
    var jets = p.jets || {};
    if (jets.sauvegardes) {
      h += '<section><h2>Jets de sauvegarde (d20 +)</h2><div class="jets">' +
        Object.keys(jets.sauvegardes).map(function (k) {
          return '<div class="jet"><div class="l">' + esc(k.slice(0, 3)) + '</div>' +
                 '<div class="v">' + esc(signed(jets.sauvegardes[k])) + '</div></div>';
        }).join('') + '</div></section>';
    }

    // Compétences (maîtrisées en surbrillance)
    if (jets.competences) {
      var mait = {};
      (p.competences || []).forEach(function (c) { if (c.maitrisee) mait[c.nom] = true; });
      var noms = Object.keys(jets.competences).sort(function (a, b) {
        return (mait[b] ? 1 : 0) - (mait[a] ? 1 : 0) || a.localeCompare(b, 'fr');
      });
      h += '<section><h2>Compétences (d20 +)</h2><div class="comps">' +
        noms.map(function (k) {
          return '<div class="comp' + (mait[k] ? ' mait' : '') + '"><span data-nom="' + esc(k) + '">' + esc(k) +
                 '</span><b>' + esc(signed(jets.competences[k])) + '</b></div>';
        }).join('') + '</div></section>';
    }

    // Blocs puces : langues, sorts
    function puces(titre, arr) {
      if (!arr || !arr.length) return '';
      return '<section><h2>' + esc(titre) + '</h2><div class="puces">' +
        arr.map(function (x) { return '<span class="puce" data-nom="' + esc(x) + '">' + esc(x) + '</span>'; }).join('') +
        '</div></section>';
    }
    h += puces('Sorts connus', p.sorts);
    h += puces('Langues', p.langues);

    // Don / outil
    if (p.don || p.outils) {
      h += '<section><h2>Don &amp; maîtrise</h2><ul class="liste">';
      if (p.don) h += '<li>' + esc(p.don) + '</li>';
      if (p.outils) h += '<li>Maîtrise d’outil : ' + esc(p.outils) + '</li>';
      h += '</ul></section>';
    }

    // Équipement
    if (p.equipement && p.equipement.length) {
      h += '<section><h2>Équipement</h2><ul class="liste">' +
        p.equipement.map(function (o) { return '<li>' + esc(o) + '</li>'; }).join('') +
        '</ul></section>';
    }

    return h;
  }


  function chargerListe() {
    return fetch('api/personnages', { headers: { 'Accept': 'application/json' }, cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var persos = (data && data.personnages) || [];
        select.innerHTML = '';
        persos.forEach(function (p) {
          var o = document.createElement('option');
          o.value = p.nom; o.textContent = p.nom + ' — ' + (p.classe || '') + ' niv. ' + (p.niveau || '?');
          select.appendChild(o);
        });
        var voulu = new URLSearchParams(location.search).get('p');
        if (voulu) select.value = voulu;
        if (!select.value && persos.length) select.value = persos[0].nom;
        if (!select.value) {
          fiche.innerHTML = '<p class="vide">Aucun personnage sauvegardé.</p>';
        } else if (voulu !== select.value) {
          // Ne navigue (rechargement) que si le paramètre diffère, sinon boucle infinie.
          location.search = 'p=' + encodeURIComponent(select.value);
        }
      })
      .catch(function (e) { fiche.innerHTML = '<p class="erreur">Liste indisponible : ' + e + '</p>'; });
  }

  function chargerFiche() {
    var nom = select.value || new URLSearchParams(location.search).get('p');
    if (!nom) return;
    fetch('api/personnages/' + encodeURIComponent(nom), { headers: { 'Accept': 'application/json' }, cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.ok) {
          fiche.innerHTML = '<p class="erreur">' + esc((data && data.erreur) || 'Erreur inconnue.') + '</p>';
          lastKey = null;
          setStatut('erreur');
          return;
        }
        // On ne re-rend que si la fiche a changé : sinon on casserait le survol
        // d'une infobulle à chaque rafraîchissement (toutes les REFRESH_MS).
        var key = JSON.stringify(data.personnage) + '|' + (data.modifie_le || '');
        if (key === lastKey) { setStatut('à jour · ' + new Date().toLocaleTimeString()); return; }
        lastKey = key;
        var pied = data.modifie_le
          ? '<div class="pied">Fiche modifiée le ' + esc(data.modifie_le) + '</div>' : '';
        fiche.innerHTML = renduFiche(data.personnage) + pied;
        appliquerInfos();
        setStatut('à jour · ' + new Date().toLocaleTimeString());
      })
      .catch(function (e) { setStatut('erreur réseau'); });
  }

  function planifier() {
    if (timer) clearInterval(timer);
    timer = setInterval(chargerFiche, REFRESH_MS);
  }

  select.addEventListener('change', function () {
    location.search = 'p=' + encodeURIComponent(select.value);
  });
  document.getElementById('refresh').addEventListener('click', function () {
    lastKey = null; chargerFiche();
  });

  // Tap tactile : affiche l'infobulle au toucher (le survol ne suffit pas sur mobile).
  var touche = null;
  document.addEventListener('click', function (e) {
    var el = e.target.closest ? e.target.closest('.info:not(.noinfo)') : null;
    if (touche && touche !== el) touche.classList.remove('show');
    if (el) { el.classList.toggle('show'); touche = el; }
    else { touche = null; }
  });

  chargerListe().then(function () { chargerFiche(); planifier(); });
})();
</script>
</body>
</html>
"""


@router.get("/api/infos", include_in_schema=False)
def infos() -> dict:
    """Descriptions courtes des sorts et compétences (pour les infobulles).

    Lecture seule, sans clé : ce ne sont que des textes du SRD, aucune donnée
    de personnage. La page panneau les charge une fois puis les met en cache.
    """
    return {
        "ok": True,
        "sorts": extract.charger_descriptions_sorts(),
        "competences": extract.DESCRIPTIONS_COMPETENCES,
    }


@router.get("/panel", include_in_schema=False)
def panneau():
    """Renvoie la page HTML autonome du panneau de fiche (lecture seule).

    Réponse en no-store : le navigateur ne doit jamais mettre la page en cache,
    sinon une ancienne version du JS resterait affichée après un redéploiement.
    """
    return HTMLResponse(
        _PAGE,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


__all__ = ["router"]
