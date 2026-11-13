"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Parametre, ResultatCorpus, Source } from "@/lib/types";

export function References({ sources, parametres }: { sources: Source[]; parametres: Parametre[] }) {
  const [q, setQ] = useState("");
  const [resultats, setResultats] = useState<ResultatCorpus[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  async function chercher(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setErreur(null);
    try {
      setResultats(await api.corpus(q));
    } catch (err) {
      setErreur((err as Error).message);
    }
  }

  return (
    <>
      <div className="section-title">
        <h2>Sources du référentiel</h2>
        <span>{sources.filter((s) => !s.verifie).length} à vérifier par l&apos;équipe</span>
      </div>
      <div className="table-wrap">
        <table className="grid">
          <tbody>
            {sources.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.url ? (
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.citation}
                    </a>
                  ) : (
                    s.citation
                  )}
                  {s.note && <div className="muted">{s.note}</div>}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {s.verifie ? <span className="badge ok">Lue</span> : <span className="badge warn">À vérifier</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">
        <h2>Hypothèses du calcul</h2>
      </div>
      <div className="table-wrap">
        <table className="grid">
          <tbody>
            {parametres.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.libelle}
                  {p.note && <div className="muted">{p.note}</div>}
                </td>
                <td className="num">
                  {p.valeur} {p.unite}
                  <div className="muted">
                    {p.bas} – {p.haut}
                  </div>
                </td>
                <td>{p.statut === "hypothese" ? <span className="badge warn">Hypothèse</span> : <span className="badge ok">Sourcée</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">
        <h2>Rechercher dans le corpus</h2>
        <span>Articles et recommandations, surtout en anglais</span>
      </div>
      <form className="search" onSubmit={chercher}>
        <label htmlFor="q-corpus" className="visually-hidden">
          Recherche dans le corpus
        </label>
        <input id="q-corpus" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ex. local anaesthesia inguinal hernia" />
        <button className="btn primary" type="submit">
          Chercher
        </button>
      </form>
      {erreur && <div className="alert error">{erreur}</div>}
      {resultats?.length === 0 && <p className="muted">Aucun résultat. Essayez des mots-clés en anglais.</p>}
      {resultats?.map((r) => (
        <div className="result" key={r.id}>
          <div>
            {r.url ? (
              <a href={r.url} target="_blank" rel="noreferrer">
                {r.citation}
              </a>
            ) : (
              r.citation
            )}{" "}
            <span className="muted">· licence {r.licence ?? "non précisée"}</span>
          </div>
          <div className="muted">{r.titre}</div>
          <p>{r.extrait}</p>
        </div>
      ))}
    </>
  );
}
