export type Fourchette = { bas: number; central: number; haut: number };

export type Source = {
  id: string;
  citation: string;
  url: string | null;
  type: string;
  corpus_id: string | null;
  verifie: boolean;
  note: string | null;
};

export type Parametre = {
  id: string;
  libelle: string;
  valeur: number;
  bas: number;
  haut: number;
  unite: string;
  statut: "source" | "hypothese";
  note: string | null;
};

export type EtapeParcours = {
  id: string;
  ordre: number;
  jour: string;
  titre: string;
  acteur: string;
  pratique_actuelle: string;
  alternatives: string[];
};

export type Parcours = {
  id: string;
  titre: string;
  description: string;
  perimetre: string;
  parametres: Parametre[];
  etapes: EtapeParcours[];
};

export type LigneImpact = {
  cle: string;
  libelle: string;
  facteur: string;
  quantite: number;
  unite: string;
  impact_kgco2e: Fourchette;
  hypothese: boolean;
  source: string;
};

export type EtapeImpact = {
  id: string;
  ordre: number;
  jour: string;
  titre: string;
  acteur: string;
  pratique_actuelle: string;
  alternatives_appliquees: string[];
  impact_kgco2e: Fourchette;
  lignes: LigneImpact[];
  part_du_total?: number;
};

export type Impact = {
  parcours: { id: string; titre: string; perimetre: string };
  unite: string;
  avant: { total: Fourchette; etapes: EtapeImpact[] };
  apres: { total: Fourchette; etapes: EtapeImpact[] };
  evite: Fourchette;
  reduction_pct: number;
  poste_principal: { etape: string; titre: string; part: number };
  annuel: { interventions: number; avant_tco2e: Fourchette; apres_tco2e: Fourchette; evite_tco2e: Fourchette };
  retenues: string[];
  part_hypotheses: number;
};

export type Alternative = {
  id: string;
  etape: string;
  titre: string;
  sous_titre: string;
  statut: "validee" | "a_discuter";
  niveau_preuve: string;
  securite: "equivalente" | "a_evaluer";
  conditions: string | null;
  vigilance: string[];
  effets_indirects: string[];
  indicateur: string | null;
  sources: Source[];
  gain_kgco2e: Fourchette;
};

export type Facteur = {
  id: string;
  libelle: string;
  valeur: number;
  bas: number;
  haut: number;
  unite: string;
  source: string;
  statut: "source" | "hypothese";
  note: string | null;
};

export type DetailCalcul = EtapeImpact & { facteurs: Record<string, Facteur> };

export type Reference = {
  numero: number;
  id: string;
  citation: string;
  url: string | null;
  nature: string;
  extrait?: string | null;
};

export type ReponseAssistant = {
  conversation_id: string;
  statut: "ok" | "bloquee" | "refus" | "tronquee" | "interrompue";
  reponse: string;
  references: Reference[];
  fiche_url: string | null;
};

export type ResultatCorpus = {
  id: string;
  titre: string;
  section: string;
  citation: string;
  url: string | null;
  licence: string | null;
  extrait: string;
};

export type Decision = "retenue" | "discussion";
export type Decisions = Record<string, Decision>;
