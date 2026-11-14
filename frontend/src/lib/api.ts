import type {
  Alternative,
  DetailCalcul,
  EtatEquipe,
  HistoriqueDecision,
  Impact,
  Parcours,
  ParametresEquipe,
  ReponseAssistant,
  ResultatCorpus,
  Sante,
  Source,
  StatutServeur,
} from "./types";

export class ErreurApi extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function requete<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!r.ok) {
    let message = `Erreur ${r.status}`;
    try {
      const corps = (await r.json()) as { detail?: unknown };
      if (typeof corps.detail === "string") message = corps.detail;
      else if (Array.isArray(corps.detail)) message = "Saisie incomplète ou invalide.";
    } catch {
      /* corps non JSON */
    }
    throw new ErreurApi(r.status, message);
  }
  return (await r.json()) as T;
}

// Équipe courante (établissement + service) : toutes les requêtes portent sur elle.
let equipe = "demo";
export const definirEquipe = (id: string) => {
  equipe = id;
};
export const equipeCourante = () => equipe;
const eq = () => `equipe=${encodeURIComponent(equipe)}`;
const base = () => `/api/equipes/${encodeURIComponent(equipe)}`;
const json = (method: string, corps: unknown): RequestInit => ({ method, body: JSON.stringify(corps) });

export const api = {
  sante: () => requete<Sante>("/api/sante"),
  parcours: () => requete<Parcours>(`/api/parcours?${eq()}`),
  alternatives: () => requete<Alternative[]>(`/api/alternatives?${eq()}`),
  sources: () => requete<Source[]>("/api/sources"),
  impact: (retenues: string[]) => requete<Impact>("/api/impact", json("POST", { retenues, equipe })),
  detailCalcul: (etape: string) => requete<DetailCalcul>(`/api/etapes/${etape}/calcul?${eq()}`),
  corpus: (q: string) => requete<ResultatCorpus[]>(`/api/corpus/recherche?q=${encodeURIComponent(q)}&k=8`),
  assistant: (question: string, conversation_id: string | null, retenues: string[]) =>
    requete<ReponseAssistant>("/api/assistant", json("POST", { question, conversation_id, retenues, equipe })),

  etat: () => requete<EtatEquipe>(`${base()}/etat`),
  decider: (alternative: string, statut: StatutServeur, auteur: string, commentaire?: string) =>
    requete<EtatEquipe>(`${base()}/decisions/${alternative}`, json("PUT", { statut, auteur, commentaire })),
  historiqueDecisions: () => requete<HistoriqueDecision[]>(`${base()}/decisions/historique`),

  parametres: () => requete<ParametresEquipe>(`${base()}/parametres`),
  saisirValeur: (parametre: string, v: { valeur: number; bas?: number; haut?: number; origine: string; auteur: string }) =>
    requete<ParametresEquipe>(`${base()}/parametres/${parametre}`, json("PUT", v)),
  retirerValeur: (parametre: string, auteur: string) =>
    requete<ParametresEquipe>(`${base()}/parametres/${parametre}?auteur=${encodeURIComponent(auteur)}`, { method: "DELETE" }),
};

export function urlFiche(retenues: string[], discussion: string[]): string {
  const q = new URLSearchParams({ equipe });
  retenues.forEach((r) => q.append("retenues", r));
  discussion.forEach((d) => q.append("discuter", d));
  return `/api/fiche?${q.toString()}`;
}

const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
export const kg = (v: number) => nf.format(v);
export const nombre = (v: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(v);
export const fourchette = (f: { bas: number; haut: number }) => `${nf.format(f.bas)} – ${nf.format(f.haut)}`;
export const dateCourte = (iso: string) =>
  new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
