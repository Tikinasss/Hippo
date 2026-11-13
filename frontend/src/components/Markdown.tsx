import { Fragment, type ReactNode } from "react";

/** Rendu minimal du markdown de l'assistant : paragraphes, listes, gras, appels de référence [n]. */
function inline(texte: string, cle: string): ReactNode[] {
  const morceaux = texte.split(/(\*\*[^*]+\*\*|\[\d+\])/g);
  return morceaux.map((m, i) => {
    const k = `${cle}-${i}`;
    if (/^\*\*[^*]+\*\*$/.test(m)) return <strong key={k}>{m.slice(2, -2)}</strong>;
    const ref = m.match(/^\[(\d+)\]$/);
    if (ref)
      return (
        <sup key={k}>
          <a href={`#ref-${ref[1]}`}>[{ref[1]}]</a>
        </sup>
      );
    return <Fragment key={k}>{m}</Fragment>;
  });
}

export function Markdown({ texte }: { texte: string }) {
  const blocs: ReactNode[] = [];
  let liste: { type: "ul" | "ol"; items: string[] } | null = null;
  const fermer = () => {
    if (!liste) return;
    const Tag = liste.type;
    const n = blocs.length;
    blocs.push(
      <Tag key={`l${n}`}>
        {liste.items.map((it, i) => (
          <li key={i}>{inline(it, `l${n}-${i}`)}</li>
        ))}
      </Tag>,
    );
    liste = null;
  };
  texte.split("\n").forEach((ligne, i) => {
    const puce = ligne.match(/^\s*[-*•]\s+(.*)$/);
    const num = ligne.match(/^\s*\d+[.)]\s+(.*)$/);
    if (puce || num) {
      const type = puce ? "ul" : "ol";
      if (liste && liste.type !== type) fermer();
      if (!liste) liste = { type, items: [] };
      liste.items.push((puce ?? num)![1]);
      return;
    }
    fermer();
    if (ligne.trim()) blocs.push(<p key={`p${i}`}>{inline(ligne.replace(/^#+\s*/, ""), `p${i}`)}</p>);
  });
  fermer();
  return <div className="md">{blocs}</div>;
}
