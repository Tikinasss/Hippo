"""Stockage PostgreSQL (+ pgvector pour les vecteurs du corpus).

Les migrations SQL de `migrations/` sont appliquées au démarrage, dans l'ordre, sous
un verrou consultatif : plusieurs instances de l'API peuvent démarrer en même temps.
"""
from __future__ import annotations

from importlib import resources

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .modeles import Decision, Equipe, ValeurLocale

_VERROU_MIGRATIONS = 4_281_917


def _date(v) -> str:
    return v.isoformat(timespec="seconds")


class StockagePostgres:
    nom = "postgres"
    nom_complet = "PostgreSQL"

    def __init__(self, url: str, migrer: bool = True) -> None:
        self.pool = ConnectionPool(url, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True)
        if migrer:
            self.migrer()

    def fermer(self) -> None:
        self.pool.close()

    # --- migrations --------------------------------------------------------------------

    def migrer(self) -> list[str]:
        fichiers = sorted((f for f in resources.files("hippo.store.migrations").iterdir() if f.name.endswith(".sql")),
                          key=lambda f: f.name)
        appliquees = []
        with self.pool.connection() as c, c.transaction():
            c.execute("SELECT pg_advisory_xact_lock(%s)", (_VERROU_MIGRATIONS,))
            c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, "
                      "appliquee_le timestamptz NOT NULL DEFAULT now())")
            faites = {r["version"] for r in c.execute("SELECT version FROM schema_migrations")}
            for f in fichiers:
                if f.name in faites:
                    continue
                c.execute(f.read_text(encoding="utf-8"))
                c.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.name,))
                appliquees.append(f.name)
        return appliquees

    # --- équipes -----------------------------------------------------------------------

    def equipes(self) -> list[Equipe]:
        with self.pool.connection() as c:
            return [Equipe.model_validate(r) for r in
                    c.execute("SELECT id, etablissement, service FROM equipes ORDER BY cree_le")]

    def equipe(self, equipe_id: str) -> Equipe | None:
        with self.pool.connection() as c:
            r = c.execute("SELECT id, etablissement, service FROM equipes WHERE id = %s", (equipe_id,)).fetchone()
        return Equipe.model_validate(r) if r else None

    def creer_equipe(self, e: Equipe) -> Equipe:
        with self.pool.connection() as c:
            c.execute("INSERT INTO equipes (id, etablissement, service) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                      (e.id, e.etablissement, e.service))
        return self.equipe(e.id)

    # --- valeurs locales ---------------------------------------------------------------

    @staticmethod
    def _valeur(r: dict) -> ValeurLocale:
        return ValeurLocale.model_construct(
            parametre=r["parametre"], valeur=r["valeur"], bas=r["bas"], haut=r["haut"], origine=r["origine"],
            auteur=r["auteur"], actif=r["actif"], date=_date(r["cree_le"]))

    def historique_valeurs(self, equipe_id: str) -> list[ValeurLocale]:
        with self.pool.connection() as c:
            return [self._valeur(r) for r in c.execute(
                "SELECT * FROM valeurs_locales WHERE equipe_id = %s ORDER BY id", (equipe_id,))]

    def valeurs_locales(self, equipe_id: str) -> list[ValeurLocale]:
        with self.pool.connection() as c:
            lignes = c.execute(
                "SELECT * FROM (SELECT DISTINCT ON (parametre) * FROM valeurs_locales WHERE equipe_id = %s "
                "ORDER BY parametre, id DESC) d WHERE actif", (equipe_id,))
            return [self._valeur(r) for r in lignes]

    def ajouter_valeur(self, equipe_id: str, v: ValeurLocale) -> None:
        with self.pool.connection() as c:
            c.execute("INSERT INTO valeurs_locales (equipe_id, parametre, valeur, bas, haut, origine, auteur, actif) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                      (equipe_id, v.parametre, v.valeur, v.bas, v.haut, v.origine, v.auteur, v.actif))

    # --- décisions ---------------------------------------------------------------------

    @staticmethod
    def _decision(r: dict) -> Decision:
        return Decision.model_construct(alternative=r["alternative"], statut=r["statut"], auteur=r["auteur"],
                                        commentaire=r["commentaire"], date=_date(r["cree_le"]))

    def historique_decisions(self, equipe_id: str) -> list[Decision]:
        with self.pool.connection() as c:
            return [self._decision(r) for r in c.execute(
                "SELECT * FROM decisions WHERE equipe_id = %s ORDER BY id", (equipe_id,))]

    def decisions(self, equipe_id: str) -> dict[str, Decision]:
        with self.pool.connection() as c:
            lignes = c.execute(
                "SELECT * FROM (SELECT DISTINCT ON (alternative) * FROM decisions WHERE equipe_id = %s "
                "ORDER BY alternative, id DESC) d WHERE statut <> 'aucune' ORDER BY id", (equipe_id,))
            return {r["alternative"]: self._decision(r) for r in lignes}

    def ajouter_decision(self, equipe_id: str, d: Decision) -> None:
        with self.pool.connection() as c:
            c.execute("INSERT INTO decisions (equipe_id, alternative, statut, auteur, commentaire) "
                      "VALUES (%s, %s, %s, %s, %s)", (equipe_id, d.alternative, d.statut, d.auteur, d.commentaire))

    # --- conversations -----------------------------------------------------------------

    def conversation(self, conversation_id: str) -> dict | None:
        with self.pool.connection() as c:
            r = c.execute("SELECT donnees, equipe_id FROM conversations WHERE id = %s", (conversation_id,)).fetchone()
        return {**r["donnees"], "equipe": r["equipe_id"]} if r else None

    def enregistrer_conversation(self, conversation_id: str, equipe_id: str, donnees: dict) -> None:
        with self.pool.connection() as c:
            c.execute("INSERT INTO conversations (id, equipe_id, donnees) VALUES (%s, %s, %s) "
                      "ON CONFLICT (id) DO UPDATE SET donnees = EXCLUDED.donnees, maj_le = now()",
                      (conversation_id, equipe_id, Jsonb(donnees)))
