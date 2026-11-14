"use client";

import { useEffect, useState } from "react";
import { api, dateCourte, kg, urlFiche } from "@/lib/api";
import type { Alternative, Decisions, HistoriqueDecision, Parcours } from "@/lib/types";

const LIBELLE_STATUT = { retenue: "retient", a_discuter: "met en discussion", aucune: "retire" } as const;

export function ActionPlan({ alternatives, decisions, parcours }: { alternatives: Alternative[]; decisions: Decisions; parcours: Parcours }) {
  const [historique, setHistorique] = useState<HistoriqueDecision[] | null>(null);
  useEffect(() => {
    api.historiqueDecisions().then(setHistorique).catch(() => setHistorique([]));
  }, [decisions]);
  const titreEtape = (id: string) => parcours.etapes.find((e) => e.id === id)?.titre ?? id;
  const retenues = alternatives.filter((a) => decisions[a.id] === "retenue");
  const discussion = alternatives.filter((a) => decisions[a.id] === "discussion");
  return (
    <>
      <div className="section-title">
        <h2>Actions retenues ({retenues.length})</h2>
        <a className="btn primary small" href={urlFiche(retenues.map((a) => a.id), discussion.map((a) => a.id))} target="_blank" rel="noreferrer">
          Ouvrir la fiche HAS
        </a>
      </div>
      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Action</th>
              <th scope="col">Étape</th>
              <th scope="col">Gain / patient</th>
              <th scope="col">Indicateur de suivi</th>
            </tr>
          </thead>
          <tbody>
            {retenues.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  Aucune action retenue. Choisissez des options dans l&apos;onglet Parcours.
                </td>
              </tr>
            )}
            {retenues.map((a) => (
              <tr key={a.id}>
                <td>
                  <strong>{a.titre}</strong>
                  <div className="muted">{a.statut === "validee" ? "Validée" : "À discuter"} · {a.niveau_preuve}</div>
                </td>
                <td>{titreEtape(a.etape)}</td>
                <td className="num">
                  <span className="gain">−{kg(a.gain_kgco2e.central)} kgCO₂e</span>
                </td>
                <td>{a.indicateur}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="section-title">
        <h2>À discuter en équipe ({discussion.length})</h2>
      </div>
      {discussion.length === 0 ? (
        <p className="muted">Aucune option mise en discussion.</p>
      ) : (
        <ul className="plain">
          {discussion.map((a) => (
            <li key={a.id}>
              <strong>{a.titre}</strong> ({titreEtape(a.etape)}) : {a.niveau_preuve}
            </li>
          ))}
        </ul>
      )}
      <div className="section-title">
        <h2>Historique des décisions</h2>
        <span>partagé par toute l&apos;équipe</span>
      </div>
      {historique === null ? (
        <p className="muted">Chargement…</p>
      ) : historique.length === 0 ? (
        <p className="muted">Aucune décision enregistrée.</p>
      ) : (
        <ul className="plain history">
          {historique.slice(0, 50).map((h, i) => (
            <li key={i}>
              <span className="muted">{dateCourte(h.date)}</span> · <strong>{h.auteur}</strong> {LIBELLE_STATUT[h.statut]} « {h.titre} »
              {h.commentaire && <span className="muted"> : {h.commentaire}</span>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
