"use client";

// Rendu markdown minimal et SÛR (sans dangerouslySetInnerHTML) pour la narration
// du MJ : paragraphes, citations (>), gras, italique, listes, titres, code.

import { Fragment, ReactNode } from "react";

function enLigne(texte: string, cle: number): ReactNode {
  // Découpe sur **gras** et *italique* (et `code`).
  const morceaux: ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let i = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = regex.exec(texte)) !== null) {
    if (m.index > i) morceaux.push(texte.slice(i, m.index));
    const t = m[0];
    if (t.startsWith("**"))
      morceaux.push(<strong key={k++}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`"))
      morceaux.push(<code key={k++}>{t.slice(1, -1)}</code>);
    else morceaux.push(<em key={k++}>{t.slice(1, -1)}</em>);
    i = m.index + t.length;
  }
  if (i < texte.length) morceaux.push(texte.slice(i));
  return <Fragment key={cle}>{morceaux}</Fragment>;
}

// Découpe une ligne de tableau GFM en cellules (sans les pipes de bord).
function cellules(ligne: string): string[] {
  let l = ligne.trim();
  if (l.startsWith("|")) l = l.slice(1);
  if (l.endsWith("|")) l = l.slice(0, -1);
  return l.split("|").map((c) => c.trim());
}

// Ligne de séparation d'en-tête de tableau : « |---|:--:| » (2+ tirets par colonne).
function est_separateur(ligne: string): boolean {
  const l = ligne.trim();
  if (!l.includes("-")) return false;
  return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/.test(l);
}

export default function Markdown({ source }: { source: string }) {
  const lignes = source.split("\n");
  const blocs: ReactNode[] = [];
  let liste: string[] = [];

  const viderListe = (cle: number) => {
    if (liste.length) {
      blocs.push(
        <ul key={`ul-${cle}`}>
          {liste.map((it, j) => (
            <li key={j}>{enLigne(it, j)}</li>
          ))}
        </ul>,
      );
      liste = [];
    }
  };

  for (let idx = 0; idx < lignes.length; idx++) {
    const l = lignes[idx].trimEnd();
    // Tableau GFM : ligne courante (avec |) + prochaine ligne non vide = séparateur.
    // Tolère les lignes vides entre l'en-tête, le séparateur et les lignes de corps.
    if (l.includes("|")) {
      let s = idx + 1;
      while (s < lignes.length && !lignes[s].trim()) s++;
      if (s < lignes.length && est_separateur(lignes[s])) {
        viderListe(idx);
        const entete = cellules(l);
        const corps: string[][] = [];
        let i = s + 1;
        while (i < lignes.length) {
          const c = lignes[i].trim();
          if (!c) {
            // Une ligne vide n'interrompt le tableau que si la suivante n'est pas une ligne.
            let n = i + 1;
            while (n < lignes.length && !lignes[n].trim()) n++;
            if (n < lignes.length && lignes[n].includes("|")) {
              i++;
              continue;
            }
            break;
          }
          if (!c.includes("|")) break;
          // Si cette ligne est elle-même l'en-tête d'un nouveau tableau
          // (suivie d'un séparateur), on s'arrête ici pour le rendre à part.
          {
            let n = i + 1;
            while (n < lignes.length && !lignes[n].trim()) n++;
            if (n < lignes.length && est_separateur(lignes[n])) break;
          }
          corps.push(cellules(lignes[i]));
          i++;
        }
        blocs.push(
          <div key={`tbl-${idx}`} className="overflow-x-auto my-2">
            <table>
              <thead>
                <tr>
                  {entete.map((c, j) => (
                    <th key={j}>{enLigne(c, j)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {corps.map((r, ri) => (
                  <tr key={ri}>
                    {entete.map((_, j) => (
                      <td key={j}>{enLigne(r[j] ?? "", j)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        );
        idx = i - 1; // le for++ reprend à la première ligne après le tableau
        continue;
      }
    }
    if (/^\s*[-*]\s+/.test(l)) {
      liste.push(l.replace(/^\s*[-*]\s+/, ""));
      continue;
    }
    viderListe(idx);
    if (!l.trim()) continue;
    if (l.startsWith("> ")) {
      blocs.push(<blockquote key={idx}>{enLigne(l.slice(2), idx)}</blockquote>);
    } else if (l.startsWith("### ")) {
      blocs.push(<h3 key={idx}>{enLigne(l.slice(4), idx)}</h3>);
    } else if (l.startsWith("## ")) {
      blocs.push(<h2 key={idx}>{enLigne(l.slice(3), idx)}</h2>);
    } else if (l.startsWith("# ")) {
      blocs.push(<h1 key={idx}>{enLigne(l.slice(2), idx)}</h1>);
    } else {
      blocs.push(<p key={idx}>{enLigne(l, idx)}</p>);
    }
  }
  viderListe(lignes.length);

  return <div className="mj-prose">{blocs}</div>;
}
