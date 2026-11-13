"use client";

import { useEffect, useState } from "react";
import { api, fourchette, kg } from "@/lib/api";
import type { Alternative, Decision, Decisions, DetailCalcul, EtapeImpact } from "@/lib/types";

type Props = {
  etape: EtapeImpact;
  alternatives: Alternative[];
  decisions: Decisions;
  onDecide: (alt: string, decision: Decision | null) => void;
  onAsk: (question: string) => void;
};

function Calcul({ etapeId }: { etapeId: string }) {
  const [detail, setDetail] = useState<DetailCalcul | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  useEffect(() => {
    api.detailCalcul(etapeId).then(setDetail).catch((e: Error) => setErreur(e.message));
  }, [etapeId]);
  if (erreur) return <p className="muted">{erreur}</p>;
  if (!detail) return <p className="muted">Chargement…</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>Poste</th>
          <th>Quantité</th>
          <th>Facteur d&apos;émission</th>
          <th>Impact (kgCO₂e)</th>
        </tr>
      </thead>
      <tbody>
        {detail.lignes.map((l) => {
          const f = detail.facteurs[l.facteur];
          return (
            <tr key={l.cle + l.facteur}>
              <td>
                {l.libelle} {l.hypothese && <span className="tag-hyp">· hypothèse</span>}
              </td>
              <td>
                {kg(l.quantite)} {l.unite}
              </td>
              <td>
                {f.libelle} : {f.valeur} kgCO₂e/{f.unite} <span className="muted">({f.bas} – {f.haut})</span>
                {f.note && <div className="muted">{f.note}</div>}
              </td>
              <td>
                {kg(l.impact_kgco2e.central)} <span className="muted">({fourchette(l.impact_kgco2e)})</span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function StepDetail({ etape, alternatives, decisions, onDecide, onAsk }: Props) {
  const alts = alternatives.filter((a) => a.etape === etape.id);
  return (
    <section className="detail" aria-labelledby="detail-titre">
      <header>
        <div>
          <h2 id="detail-titre">{etape.titre} : options d&apos;optimisation</h2>
          <div className="muted">
            Pratique actuelle : {etape.pratique_actuelle} · {kg(etape.impact_kgco2e.central)} kgCO₂e par patient (
            {fourchette(etape.impact_kgco2e)})
          </div>
        </div>
        <button type="button" className="btn small outline" onClick={() => onAsk(`Que puis-je changer à l'étape « ${etape.titre} » sans risque pour le patient ?`)}>
          Demander à l&apos;assistant
        </button>
      </header>
      {alts.length === 0 ? (
        <p className="muted" style={{ padding: "12px 14px", margin: 0 }}>
          Aucune alternative documentée pour cette étape dans la base actuelle.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">Option</th>
                <th scope="col">Source</th>
                <th scope="col">Qualité et sécurité</th>
                <th scope="col">Impact évité</th>
                <th scope="col">Décision</th>
              </tr>
            </thead>
            <tbody>
              {alts.map((a) => {
                const d = decisions[a.id];
                return (
                  <tr key={a.id}>
                    <td>
                      <strong>{a.titre}</strong>
                      <div className="muted">{a.sous_titre}</div>
                      {a.conditions && <div className="muted">Conditions : {a.conditions}</div>}
                    </td>
                    <td style={{ maxWidth: 260 }}>
                      <span className={`badge ${a.statut === "validee" ? "ok" : "discuss"}`}>
                        {a.statut === "validee" ? "Validée" : "À discuter"}
                      </span>
                      <div className="muted">{a.niveau_preuve}</div>
                      <div className="muted">
                        {a.sources.map((s, i) => (
                          <span key={s.id}>
                            {i > 0 && " · "}
                            {s.url ? (
                              <a href={s.url} target="_blank" rel="noreferrer">
                                {s.citation.split(",")[0]}
                              </a>
                            ) : (
                              s.citation.split(",")[0]
                            )}
                            {!s.verifie && " (à vérifier)"}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td style={{ maxWidth: 240 }}>
                      <strong style={{ color: a.securite === "equivalente" ? "var(--green)" : "var(--amber)" }}>
                        {a.securite === "equivalente" ? "Équivalente" : "À évaluer"}
                      </strong>
                      {a.vigilance.length > 0 && <div className="muted">Vigilance : {a.vigilance.join(" ; ")}</div>}
                    </td>
                    <td className="num">
                      <span className="gain">−{kg(a.gain_kgco2e.central)} kgCO₂e</span>
                      <div className="muted">{fourchette(a.gain_kgco2e)}</div>
                    </td>
                    <td>
                      <div className="decision">
                        <button
                          type="button"
                          className="btn small"
                          aria-pressed={d === "retenue"}
                          onClick={() => onDecide(a.id, d === "retenue" ? null : "retenue")}
                        >
                          {d === "retenue" ? "Retenue" : "Retenir"}
                        </button>
                        <button
                          type="button"
                          className="btn small discuss"
                          aria-pressed={d === "discussion"}
                          onClick={() => onDecide(a.id, d === "discussion" ? null : "discussion")}
                        >
                          {d === "discussion" ? "En staff" : "Proposer en staff"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <details className="calc">
        <summary>Expliquer le calcul de cette étape</summary>
        <Calcul etapeId={etape.id} />
      </details>
    </section>
  );
}
