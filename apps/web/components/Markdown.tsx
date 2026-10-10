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

  lignes.forEach((ligne, idx) => {
    const l = ligne.trimEnd();
    if (/^\s*[-*]\s+/.test(l)) {
      liste.push(l.replace(/^\s*[-*]\s+/, ""));
      return;
    }
    viderListe(idx);
    if (!l.trim()) return;
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
  });
  viderListe(lignes.length);

  return <div className="mj-prose">{blocs}</div>;
}
