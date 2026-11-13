import type {
  Alternative,
  DetailCalcul,
  Impact,
  Parcours,
  ReponseAssistant,
  ResultatCorpus,
  Source,
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
    } catch {
      /* corps non JSON */
    }
    throw new ErreurApi(r.status, message);
  }
  return (await r.json()) as T;
}

export const api = {
  parcours: () => requete<Parcours>("/api/parcours"),
  alternatives: () => requete<Alternative[]>("/api/alternatives"),
  sources: () => requete<Source[]>("/api/sources"),
  impact: (retenues: string[]) =>
    requete<Impact>("/api/impact", { method: "POST", body: JSON.stringify({ retenues }) }),
  detailCalcul: (etape: string) => requete<DetailCalcul>(`/api/etapes/${etape}/calcul`),
  corpus: (q: string) => requete<ResultatCorpus[]>(`/api/corpus/recherche?q=${encodeURIComponent(q)}&k=8`),
  assistant: (question: string, conversation_id: string | null, retenues: string[]) =>
    requete<ReponseAssistant>("/api/assistant", {
      method: "POST",
      body: JSON.stringify({ question, conversation_id, retenues }),
    }),
};

export function urlFiche(retenues: string[], discussion: string[]): string {
  const q = new URLSearchParams();
  retenues.forEach((r) => q.append("retenues", r));
  discussion.forEach((d) => q.append("discuter", d));
  return `/api/fiche?${q.toString()}`;
}

const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
export const kg = (v: number) => nf.format(v);
export const fourchette = (f: { bas: number; haut: number }) => `${nf.format(f.bas)} – ${nf.format(f.haut)}`;
