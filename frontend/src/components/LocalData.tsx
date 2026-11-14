"use client";

import { useEffect, useState } from "react";
import { api, dateCourte, nombre } from "@/lib/api";
import type { ParametreEquipe, ParametresEquipe } from "@/lib/types";

type Props = {
  auteur: string;
  onChange: () => void; // recalcul du parcours après une saisie
  onErreur: (message: string) => void;
};

type Brouillon = { valeur: string; bas: string; haut: string; origine: string };

const lireNombre = (s: string) => (s.trim() === "" ? undefined : Number(s.replace(",", ".")));

function Formulaire({ p, auteur, onFini, onErreur }: { p: ParametreEquipe; auteur: string; onFini: (d: ParametresEquipe | null) => void; onErreur: (m: string) => void }) {
  const init = p.local;
  const [b, setB] = useState<Brouillon>({
    valeur: init?.valeur != null ? String(init.valeur) : "",
    bas: init?.bas != null && init.bas !== init.valeur ? String(init.bas) : "",
    haut: init?.haut != null && init.haut !== init.valeur ? String(init.haut) : "",
    origine: init?.origine ?? "",
  });
  const [envoi, setEnvoi] = useState(false);

  async function enregistrer(e: React.FormEvent) {
    e.preventDefault();
    if (!auteur) return onErreur("Indiquez votre nom en haut de la page : chaque saisie est tracée.");
    const valeur = lireNombre(b.valeur);
    if (valeur === undefined || Number.isNaN(valeur)) return onErreur("Saisissez une valeur numérique.");
    setEnvoi(true);
    try {
      onFini(await api.saisirValeur(p.id, { valeur, bas: lireNombre(b.bas), haut: lireNombre(b.haut), origine: b.origine.trim(), auteur }));
    } catch (err) {
      onErreur((err as Error).message);
    } finally {
      setEnvoi(false);
    }
  }

  const champ = (cle: keyof Brouillon, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="field">
      <span>{label}</span>
      <input value={b[cle]} onChange={(e) => setB({ ...b, [cle]: e.target.value })} {...props} />
    </label>
  );

  return (
    <form className="local-form" onSubmit={enregistrer}>
      <div className="fields">
        {champ("valeur", `Valeur (${p.unite})`, { inputMode: "decimal", required: true, autoFocus: true })}
        {champ("bas", "Borne basse (facultatif)", { inputMode: "decimal" })}
        {champ("haut", "Borne haute (facultatif)", { inputMode: "decimal" })}
      </div>
      {champ("origine", "Origine de la donnée", { required: true, placeholder: "ex. DIM, codes postaux des patients 2025" })}
      <div className="decision">
        <button className="btn primary small" type="submit" disabled={envoi}>
          Enregistrer
        </button>
        <button className="btn small" type="button" onClick={() => onFini(null)}>
          Annuler
        </button>
      </div>
    </form>
  );
}

export function LocalData({ auteur, onChange, onErreur }: Props) {
  const [donnees, setDonnees] = useState<ParametresEquipe | null>(null);
  const [edition, setEdition] = useState<string | null>(null);

  useEffect(() => {
    api.parametres().then(setDonnees).catch((e: Error) => onErreur(e.message));
  }, [onErreur]);

  function maj(d: ParametresEquipe | null) {
    setEdition(null);
    if (d) {
      setDonnees(d);
      onChange();
    }
  }

  async function retirer(p: ParametreEquipe) {
    if (!auteur) return onErreur("Indiquez votre nom en haut de la page : chaque saisie est tracée.");
    try {
      maj(await api.retirerValeur(p.id, auteur));
    } catch (e) {
      onErreur((e as Error).message);
    }
  }

  if (!donnees) return <p className="muted">Chargement des données locales…</p>;
  const nLocales = donnees.parametres.filter((p) => p.local).length;

  return (
    <>
      <div className="alert info">
        <span>
          Le calcul repose encore à <strong>{Math.round(100 * donnees.part_hypotheses)} %</strong> sur des hypothèses. Remplacez-les par
          les valeurs réelles du service (DIM, services techniques, pharmacie) : chaque saisie est datée, signée et réversible.
        </span>
      </div>
      <div className="section-title">
        <h2>Paramètres du parcours</h2>
        <span>
          {nLocales} sur {donnees.parametres.length} renseignés avec une donnée locale
        </span>
      </div>
      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Paramètre</th>
              <th scope="col">Hypothèse de départ</th>
              <th scope="col">Valeur du service</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {donnees.parametres.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.libelle}
                  {p.reference.note && <div className="muted">{p.reference.note}</div>}
                  {edition === p.id && <Formulaire p={p} auteur={auteur} onFini={maj} onErreur={onErreur} />}
                </td>
                <td className="num">
                  {nombre(p.reference.valeur)} {p.unite}
                  <div className="muted">
                    {nombre(p.reference.bas)} – {nombre(p.reference.haut)}
                    {p.reference.statut === "source" ? " · sourcée" : ""}
                  </div>
                </td>
                <td className="num">
                  {p.local ? (
                    <>
                      <span className="badge ok">
                        {nombre(p.local.valeur ?? 0)} {p.unite}
                      </span>
                      {p.local.bas !== p.local.haut && (
                        <div className="muted">
                          {nombre(p.local.bas ?? 0)} – {nombre(p.local.haut ?? 0)}
                        </div>
                      )}
                      <div className="muted">{p.local.origine}</div>
                      <div className="muted">
                        {p.local.auteur} · {dateCourte(p.local.date)}
                      </div>
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {edition !== p.id && (
                    <div className="decision">
                      <button className="btn small outline" type="button" onClick={() => setEdition(p.id)}>
                        {p.local ? "Modifier" : "Saisir"}
                      </button>
                      {p.local && (
                        <button className="btn small" type="button" onClick={() => void retirer(p)} title="Revenir à l'hypothèse de départ">
                          Hypothèse
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">
        <h2>Historique des saisies</h2>
      </div>
      {donnees.historique.length === 0 ? (
        <p className="muted">Aucune saisie pour l&apos;instant.</p>
      ) : (
        <ul className="plain history">
          {donnees.historique.map((h, i) => (
            <li key={i}>
              <span className="muted">{dateCourte(h.date)}</span> · <strong>{h.auteur}</strong> ·{" "}
              {h.actif === false ? (
                <>remet l&apos;hypothèse pour « {h.libelle} »</>
              ) : (
                <>
                  « {h.libelle} » = {nombre(h.valeur ?? 0)} ({h.origine})
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
