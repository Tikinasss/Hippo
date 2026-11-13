import type { Fourchette } from "@/lib/types";
import { fourchette, kg } from "@/lib/api";

/** Barre de valeur centrale + moustache bas–haut, sur une échelle commune `max`. */
export function ImpactBar({ f, max, couleur = "var(--serie-actuel)" }: { f: Fourchette; max: number; couleur?: string }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (100 * v) / max))}%`;
  return (
    <div className="impact-cell" title={`${kg(f.central)} kgCO₂e (fourchette ${fourchette(f)})`}>
      <div className="bar" style={{ flex: 1 }} aria-hidden="true">
        <div className="track" />
        <div className="fill" style={{ width: pct(f.central), background: couleur }} />
        <div className="whisker" style={{ left: pct(f.bas), width: `calc(${pct(f.haut)} - ${pct(f.bas)})` }} />
      </div>
      <span className="v">{kg(f.central)}</span>
    </div>
  );
}
