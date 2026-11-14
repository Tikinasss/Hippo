"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ActionPlan } from "@/components/ActionPlan";
import { AssistantPanel } from "@/components/AssistantPanel";
import { Comparison } from "@/components/Comparison";
import { LocalData } from "@/components/LocalData";
import { References } from "@/components/References";
import { StepDetail } from "@/components/StepDetail";
import { StepsTable } from "@/components/StepsTable";
import { api, definirEquipe, ErreurApi, fourchette, kg, urlFiche } from "@/lib/api";
import type { Alternative, Decision, Decisions, Equipe, EtatEquipe, Impact, Parcours, Source } from "@/lib/types";

const CLE_AUTEUR = "hippo.auteur";
const SCENARIO_DEMO: Decisions = {
  regroupement_consultations: "retenue",
  bilan_cible: "retenue",
  aivoc: "retenue",
  ordonnance_ajustee: "retenue",
  teleconsultation_suivi: "retenue",
  kit_optimise: "discussion",
  transport_accompagnant: "discussion",
};
type Onglet = "parcours" | "comparaison" | "plan" | "donnees" | "references";

// Décisions telles qu'enregistrées par l'équipe (base partagée) -> état de l'écran
function versDecisions(etat: EtatEquipe): Decisions {
  return Object.fromEntries([
    ...etat.retenues.map((a) => [a, "retenue"] as const),
    ...etat.a_discuter.map((a) => [a, "discussion"] as const),
  ]);
}

function lireAuteur(): string {
  try {
    return localStorage.getItem(CLE_AUTEUR) ?? "";
  } catch {
    return "";
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
  const [equipe, setEquipe] = useState<Equipe | null>(null);
  const [auteur, setAuteur] = useState("");
  const [enCours, setEnCours] = useState(false);

  const retenues = useMemo(() => Object.keys(decisions).filter((k) => decisions[k] === "retenue"), [decisions]);
  const discussion = useMemo(() => Object.keys(decisions).filter((k) => decisions[k] === "discussion"), [decisions]);

  // Charge le parcours (avec les valeurs locales de l'équipe), les options, les sources et les décisions.
  const charger = useCallback(async () => {
    const [p, a, s, etat] = await Promise.all([api.parcours(), api.alternatives(), api.sources(), api.etat()]);
    const d = versDecisions(etat);
    const imp = await api.impact(Object.keys(d).filter((k) => d[k] === "retenue"));
    setParcours(p);
    setAlternatives(a);
    setSources(s);
    setEquipe(etat.equipe);
    setDecisions(d);
    setImpact(imp);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    definirEquipe(params.get("equipe") ?? "demo");
    const ongletUrl = params.get("onglet") as Onglet | null;
    if (ongletUrl && ["parcours", "comparaison", "plan", "donnees", "references"].includes(ongletUrl)) setOnglet(ongletUrl);
    setAuteur(lireAuteur());
    charger()
      .then(() => setErreur(null))
      .catch((e) =>
        setErreur(
          e instanceof ErreurApi && e.status === 404
            ? e.message
            : "Impossible de joindre l'API Hippo. Lancez le backend : uvicorn hippo.api.main:app --port 8000",
        ),
      );
    // les décisions sont partagées : on se resynchronise quand on revient sur l'onglet du navigateur
    const auRetour = () => {
      if (document.visibilityState === "visible") charger().catch(() => undefined);
    };
    document.addEventListener("visibilitychange", auRetour);
    return () => document.removeEventListener("visibilitychange", auRetour);
  }, [charger]);

  function changerAuteur(nom: string) {
    setAuteur(nom);
    try {
      localStorage.setItem(CLE_AUTEUR, nom);
    } catch {
      /* stockage indisponible : le nom reste pour la session */
    }
  }

  function exigerAuteur() {
    if (auteur.trim()) return true;
    setErreur("Indiquez votre nom en haut de la page : chaque décision est enregistrée à votre nom.");
    document.getElementById("auteur")?.focus();
    return false;
  }

  async function appliquer(changements: [string, Decision | null][]) {
    if (!exigerAuteur()) return;
    setEnCours(true);
    try {
      let etat: EtatEquipe | null = null;
      for (const [alt, decision] of changements) {
        const statut = decision === "retenue" ? "retenue" : decision === "discussion" ? "a_discuter" : "aucune";
        etat = await api.decider(alt, statut, auteur.trim());
      }
      if (etat) {
        const d = versDecisions(etat);
        setDecisions(d);
        setImpact(await api.impact(Object.keys(d).filter((k) => d[k] === "retenue")));
      }
      setErreur(null);
    } catch (e) {
      setErreur(e instanceof ErreurApi && e.status === 409 ? e.message : (e as Error).message);
      await charger().catch(() => undefined);
    } finally {
      setEnCours(false);
    }
  }

  function decider(alt: string, decision: Decision | null) {
    void appliquer([[alt, decision]]);
  }

  function chargerScenario(cible: Decisions) {
    // on retire d'abord ce qui n'est pas dans la cible (évite un conflit transitoire), puis on applique la cible
    const retraits = Object.keys(decisions)
      .filter((a) => !(a in cible))
      .map((a) => [a, null] as [string, Decision | null]);
    const ajouts = Object.entries(cible).filter(([a, d]) => decisions[a] !== d) as [string, Decision | null][];
    void appliquer([...retraits, ...ajouts]);
  }

  const surErreur = useCallback((m: string) => setErreur(m), []);
  const apresSaisie = useCallback(() => {
    charger().catch((e: Error) => setErreur(e.message));
  }, [charger]);

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
        <span className="context">{equipe ? `${equipe.service} · ${equipe.etablissement}` : ""}</span>
        <label className="whoami">
          <span>Vous êtes</span>
          <input id="auteur" value={auteur} onChange={(e) => changerAuteur(e.target.value)} placeholder="Nom, fonction" maxLength={120} />
        </label>
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
              <button type="button" disabled={enCours} onClick={() => chargerScenario(SCENARIO_DEMO)}>
                Charger le scénario de démo
              </button>
            </li>
            <li>
              <button type="button" disabled={enCours} onClick={() => chargerScenario({})}>
                Revenir au parcours actuel
              </button>
            </li>
          </ul>
        </nav>

        <main className="main">
          <div className="crumbs">Parcours de soins › {equipe?.service ?? "Chirurgie ambulatoire"}</div>
          <div className="page-head">
            <div>
              <h1>{parcours?.titre ?? "Cure de hernie inguinale"}</h1>
              <p>
                {parcours?.description ?? "Parcours ambulatoire"}{" "}
                {impact && impact.part_hypotheses > 0 && (
                  <button
                    type="button"
                    className="badge demo as-link"
                    onClick={() => setOnglet("donnees")}
                    title="Remplacer les hypothèses par les valeurs réelles du service"
                  >
                    {Math.round(100 * impact.part_hypotheses)} % d&apos;hypothèses à valider
                  </button>
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
                ["donnees", "Données locales"],
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
          {parcours && onglet === "donnees" && <LocalData auteur={auteur.trim()} onChange={apresSaisie} onErreur={surErreur} />}
          {parcours && onglet === "references" && <References sources={sources} parametres={parcours.parametres} />}
        </main>

        <AssistantPanel retenues={retenues} question={question} open={panneau} onClose={() => setPanneau(false)} />
      </div>
    </div>
  );
}
