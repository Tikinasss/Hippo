import { fourchette, kg } from "@/lib/api";
import type { Impact } from "@/lib/types";

export function Comparison({ impact }: { impact: Impact }) {
  const max = Math.max(...impact.avant.etapes.map((e) => e.impact_kgco2e.central), 1);
  const w = (v: number) => `${(100 * v) / max}%`;
  const an = impact.annuel;
  return (
    <>
      <div className="cards-2">
        <div className="box">
          <h3>Par patient</h3>
          <div className="big">
            {kg(impact.avant.total.central)} → {kg(impact.apres.total.central)} kgCO₂e
          </div>
          <div className="muted">
            Évité : {kg(impact.evite.central)} kgCO₂e (fourchette {fourchette(impact.evite)}), soit −{kg(impact.reduction_pct)} %
          </div>
        </div>
        <div className="box">
          <h3>Sur un an, pour {an.interventions} interventions</h3>
          <div className="big">{kg(an.evite_tco2e.central)} tCO₂e évitées</div>
          <div className="muted">
            Fourchette {fourchette(an.evite_tco2e)} tCO₂e · nombre d&apos;interventions à remplacer par celui du service
          </div>
        </div>
      </div>

      <div className="section-title">
        <h2>Avant / après, par étape</h2>
        <div className="legend" aria-hidden="true">
          <span>
            <i style={{ background: "var(--serie-actuel)" }} />
            Actuel
          </span>
          <span>
            <i style={{ background: "var(--serie-optimise)" }} />
            Optimisé
          </span>
        </div>
      </div>
      <div className="table-wrap" role="table" aria-label="Impact par étape avant et après optimisation, en kgCO₂e par patient">
        {impact.avant.etapes.map((e, i) => {
          const apres = impact.apres.etapes[i];
          const change = Math.abs(apres.impact_kgco2e.central - e.impact_kgco2e.central) > 0.05;
          return (
            <div className="compare-row" role="row" key={e.id}>
              <div role="rowheader">
                <strong>{e.titre}</strong>
                <div className="muted">{e.jour}</div>
              </div>
              <div className="compare-bars" role="cell">
                <div className="b" title={`Actuel : ${kg(e.impact_kgco2e.central)} kgCO₂e (${fourchette(e.impact_kgco2e)})`}>
                  <span className="f" style={{ width: w(e.impact_kgco2e.central), background: "var(--serie-actuel)" }} />
                  <span className="t">{kg(e.impact_kgco2e.central)}</span>
                </div>
                <div className="b" title={`Optimisé : ${kg(apres.impact_kgco2e.central)} kgCO₂e (${fourchette(apres.impact_kgco2e)})`}>
                  <span className="f" style={{ width: w(apres.impact_kgco2e.central), background: "var(--serie-optimise)" }} />
                  <span className="t">
                    {kg(apres.impact_kgco2e.central)}
                    {change && <span className="gain"> (−{kg(e.impact_kgco2e.central - apres.impact_kgco2e.central)})</span>}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <p className="muted">
        Les fourchettes combinent les bornes basses et hautes des facteurs d&apos;émission et des hypothèses. {Math.round(100 * impact.part_hypotheses)} %
        de l&apos;impact actuel repose sur au moins une hypothèse à valider. Périmètre : {impact.parcours.perimetre}
      </p>
    </>
  );
}
