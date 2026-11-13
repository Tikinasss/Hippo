"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ActionPlan } from "@/components/ActionPlan";
import { AssistantPanel } from "@/components/AssistantPanel";
import { Comparison } from "@/components/Comparison";
import { References } from "@/components/References";
import { StepDetail } from "@/components/StepDetail";
import { StepsTable } from "@/components/StepsTable";
import { api, ErreurApi, fourchette, kg, urlFiche } from "@/lib/api";
import type { Alternative, Decision, Decisions, Impact, Parcours, Source } from "@/lib/types";

const CLE_STOCKAGE = "hippo.decisions.v1";
const SCENARIO_DEMO: Decisions = {
  regroupement_consultations: "retenue",
  bilan_cible: "retenue",
  aivoc: "retenue",
  ordonnance_ajustee: "retenue",
  teleconsultation_suivi: "retenue",
  kit_optimise: "discussion",
  transport_accompagnant: "discussion",
};
type Onglet = "parcours" | "comparaison" | "plan" | "references";

function lireDecisions(): Decisions {
  try {
    return JSON.parse(localStorage.getItem(CLE_STOCKAGE) ?? "{}") as Decisions;
  } catch {
    return {};
  }
}

export default function Page() {
  const [parcours, setParcours] = useState<Parcours | null>(null);
  const [alternatives, setAlternatives] = useState<Alternative[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [decisions, setDecisions] = useState<Decisions>({});
  const [selection, setSelection] = useState<string | null>("bloc_operatoire");
  const [onglet, setOnglet] = useState<Onglet>("parcours");
  const [erreur, setErreur] = useState<string | null>(null);
  const [panneau, setPanneau] = useState(false);
  const [question, setQuestion] = useState<{ texte: string; n: number } | null>(null);

  const retenues = useMemo(() => Object.keys(decisions).filter((k) => decisions[k] === "retenue"), [decisions]);
  const discussion = useMemo(() => Object.keys(decisions).filter((k) => decisions[k] === "discussion"), [decisions]);

  useEffect(() => {
    Promise.all([api.parcours(), api.alternatives(), api.sources()])
      .then(([p, a, s]) => {
        setParcours(p);
        setAlternatives(a);
        setSources(s);
        const ids = new Set(a.map((x) => x.id));
        const demo = new URLSearchParams(window.location.search).get("scenario") === "demo";
        setDecisions(demo ? SCENARIO_DEMO : Object.fromEntries(Object.entries(lireDecisions()).filter(([k]) => ids.has(k))));
      })
      .catch(() => setErreur("Impossible de joindre l'API Hippo. Lancez le backend : uvicorn hippo.api.main:app --port 8000"));
  }, []);

  const recalculer = useCallback(async (d: Decisions, precedentes: Decisions) => {
    const ret = Object.keys(d).filter((k) => d[k] === "retenue");
    try {
      setImpact(await api.impact(ret));
      setDecisions(d);
      try {
        localStorage.setItem(CLE_STOCKAGE, JSON.stringify(d));
      } catch {
        /* stockage indisponible : la session continue sans mémorisation */
      }
      setErreur(null);
    } catch (e) {
      setDecisions(precedentes);
      setErreur(e instanceof ErreurApi && e.status === 409 ? e.message : (e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (parcours) void recalculer(decisions, {});
    // premier calcul une fois les données chargées
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parcours]);

  function decider(alt: string, decision: Decision | null) {
    const suivantes = { ...decisions };
    if (decision) suivantes[alt] = decision;
    else delete suivantes[alt];
    void recalculer(suivantes, decisions);
  }

  function demander(texte: string) {
    setPanneau(true);
    setQuestion((q) => ({ texte, n: (q?.n ?? 0) + 1 }));
  }

  const etapeSelectionnee = impact?.avant.etapes.find((e) => e.id === selection);
  const securite = alternatives.filter((a) => decisions[a.id] === "retenue").every((a) => a.securite === "equivalente");

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>Hippo</strong>
          <span>Écoconception des parcours de soins</span>
        </div>
        <div className="spacer" />
        <span className="context">Chirurgie ambulatoire · CHU de démonstration</span>
        <button type="button" className="btn small outline panel-toggle" onClick={() => setPanneau((o) => !o)} aria-expanded={panneau}>
          Assistant
        </button>
      </header>

      <div className="body">
        <nav className="sidebar" aria-label="Parcours">
          <h2>Mes parcours</h2>
          <ul>
            <li>
              <button type="button" aria-current="page">
                Cure de hernie inguinale
              </button>
            </li>
            {["Chirurgie de la cataracte", "Arthroscopie du genou", "Amygdalectomie de l'enfant"].map((p) => (
              <li key={p}>
                <span className="item">
                  {p} <small>bientôt</small>
                </span>
              </li>
            ))}
          </ul>
          <h2>Démonstration</h2>
          <ul>
            <li>
              <button type="button" onClick={() => void recalculer(SCENARIO_DEMO, decisions)}>
                Charger le scénario de démo
              </button>
            </li>
            <li>
              <button type="button" onClick={() => void recalculer({}, decisions)}>
                Revenir au parcours actuel
              </button>
            </li>
          </ul>
        </nav>

        <main className="main">
          <div className="crumbs">Parcours de soins › Chirurgie ambulatoire</div>
          <div className="page-head">
            <div>
              <h1>{parcours?.titre ?? "Cure de hernie inguinale"}</h1>
              <p>
                {parcours?.description ?? "Parcours ambulatoire"}{" "}
                {impact && impact.part_hypotheses > 0.5 && (
                  <span className="badge demo" title="Une partie des valeurs repose sur des hypothèses à valider">
                    {Math.round(100 * impact.part_hypotheses)} % d&apos;hypothèses à valider
                  </span>
                )}
              </p>
            </div>
            <div className="actions">
              <a className="btn primary" href={urlFiche(retenues, discussion)} target="_blank" rel="noreferrer">
                Exporter la fiche HAS
              </a>
            </div>
          </div>

          {erreur && (
            <div className="alert error" role="alert">
              <span>{erreur}</span>
              <button type="button" onClick={() => setErreur(null)} aria-label="Fermer le message">
                ×
              </button>
            </div>
          )}

          <div className="tabs" role="tablist">
            {(
              [
                ["parcours", "Parcours"],
                ["comparaison", "Comparaison avant / après"],
                ["plan", `Plan d'action (${retenues.length})`],
                ["references", "Références"],
              ] as [Onglet, string][]
            ).map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={onglet === id} onClick={() => setOnglet(id)}>
                {label}
              </button>
            ))}
          </div>

          {impact && (
            <div className="kpis">
              <div className="kpi">
                <div className="label">Impact actuel</div>
                <div className="value">
                  {kg(impact.avant.total.central)} <small>kgCO₂e / patient</small>
                </div>
                <div className="sub">Fourchette {fourchette(impact.avant.total)}</div>
              </div>
              <div className="kpi">
                <div className="label">Après optimisation</div>
                <div className="value">
                  {kg(impact.apres.total.central)} <small>kgCO₂e / patient</small>
                </div>
                <div className={`sub${impact.reduction_pct > 0 ? " good" : ""}`}>
                  {retenues.length === 0
                    ? "Aucune option retenue"
                    : `−${kg(impact.reduction_pct)} % · fourchette ${fourchette(impact.apres.total)}`}
                </div>
              </div>
              <div className="kpi">
                <div className="label">Recommandations retenues</div>
                <div className="value">
                  {retenues.length} <small>sur {alternatives.length}</small>
                </div>
                <div className="sub">{discussion.length} à discuter en équipe</div>
              </div>
              <div className="kpi">
                <div className="label">Qualité et sécurité des soins</div>
                {retenues.length === 0 ? (
                  <>
                    <div className="value">Inchangées</div>
                    <div className="sub">aucune option retenue</div>
                  </>
                ) : (
                  <>
                    <div className="value" style={{ color: securite ? "var(--green)" : "var(--amber)" }}>
                      {securite ? "Équivalentes" : "À évaluer"}
                    </div>
                    <div className="sub">selon les sources citées</div>
                  </>
                )}
              </div>
            </div>
          )}

          {!impact && !erreur && <p className="muted">Chargement du parcours…</p>}

          {impact && parcours && onglet === "parcours" && (
            <>
              <StepsTable impact={impact} alternatives={alternatives} decisions={decisions} selection={selection} onSelect={setSelection} />
              {etapeSelectionnee && (
                <StepDetail etape={etapeSelectionnee} alternatives={alternatives} decisions={decisions} onDecide={decider} onAsk={demander} />
              )}
            </>
          )}
          {impact && onglet === "comparaison" && <Comparison impact={impact} />}
          {parcours && onglet === "plan" && <ActionPlan alternatives={alternatives} decisions={decisions} parcours={parcours} />}
          {parcours && onglet === "references" && <References sources={sources} parametres={parcours.parametres} />}
        </main>

        <AssistantPanel retenues={retenues} question={question} open={panneau} onClose={() => setPanneau(false)} />
      </div>
    </div>
  );
}
