import type { Alternative, Decisions, EtapeImpact, Impact } from "@/lib/types";
import { kg } from "@/lib/api";
import { ImpactBar } from "./ImpactBar";

type Props = {
  impact: Impact;
  alternatives: Alternative[];
  decisions: Decisions;
  selection: string | null;
  onSelect: (etape: string) => void;
};

function Optimisation({ etape, alternatives, decisions }: { etape: EtapeImpact; alternatives: Alternative[]; decisions: Decisions }) {
  const alts = alternatives.filter((a) => a.etape === etape.id);
  const retenues = alts.filter((a) => decisions[a.id] === "retenue");
  const discussion = alts.filter((a) => decisions[a.id] === "discussion");
  if (alts.length === 0) return <span className="muted">Aucune alternative documentée</span>;
  if (retenues.length === 0 && discussion.length === 0) {
    const validees = alts.filter((a) => a.statut === "validee").length;
    return (
      <span className="muted">
        {alts.length} option{alts.length > 1 ? "s" : ""}
        {validees ? ` · ${validees} validée${validees > 1 ? "s" : ""}` : " à discuter"}
      </span>
    );
  }
  return (
    <div>
      {retenues.map((a) => (
        <div key={a.id}>
          {a.titre} <span className="badge ok">retenue</span>{" "}
          <span className="gain">−{kg(a.gain_kgco2e.central)} kg</span>
        </div>
      ))}
      {discussion.map((a) => (
        <div key={a.id}>
          {a.titre} <span className="badge discuss">en staff</span>
        </div>
      ))}
    </div>
  );
}

export function StepsTable({ impact, alternatives, decisions, selection, onSelect }: Props) {
  const max = Math.max(...impact.avant.etapes.map((e) => e.impact_kgco2e.haut));
  return (
    <>
      <div className="section-title">
        <h2>Étapes du parcours</h2>
        <span>Impact actuel en kgCO₂e par patient · barre = valeur centrale, trait = fourchette</span>
      </div>
      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Temps</th>
              <th scope="col">Étape de soins</th>
              <th scope="col">Pratique actuelle</th>
              <th scope="col">Impact env.</th>
              <th scope="col">Optimisation</th>
            </tr>
          </thead>
          <tbody>
            {impact.avant.etapes.map((e) => (
              <tr
                key={e.id}
                className={`clickable${selection === e.id ? " selected" : ""}`}
                onClick={() => onSelect(e.id)}
              >
                <td className="day">{e.jour}</td>
                <td>
                  <button type="button" className="rowlink" onClick={() => onSelect(e.id)} aria-expanded={selection === e.id}>
                    {e.titre}
                  </button>
                  <div className="muted">{e.acteur}</div>
                  {impact.poste_principal.etape === e.id && (
                    <span className="badge warn">Poste principal ({Math.round(100 * impact.poste_principal.part)} %)</span>
                  )}
                </td>
                <td>{e.pratique_actuelle}</td>
                <td style={{ minWidth: 200 }}>
                  <ImpactBar f={e.impact_kgco2e} max={max} />
                </td>
                <td>
                  <Optimisation etape={e} alternatives={alternatives} decisions={decisions} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
