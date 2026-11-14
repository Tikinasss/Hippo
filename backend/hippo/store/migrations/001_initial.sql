-- Schéma initial d'Hippo : équipes, journaux de valeurs locales et de décisions,
-- conversations de l'assistant, vecteurs du corpus (pgvector).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE equipes (
    id            text PRIMARY KEY,
    etablissement text NOT NULL,
    service       text NOT NULL,
    cree_le       timestamptz NOT NULL DEFAULT now()
);

-- Journal en ajout seul : la valeur courante est la dernière ligne par paramètre.
CREATE TABLE valeurs_locales (
    id        bigserial PRIMARY KEY,
    equipe_id text NOT NULL REFERENCES equipes (id) ON DELETE CASCADE,
    parametre text NOT NULL,
    valeur    double precision,
    bas       double precision,
    haut      double precision,
    origine   text,
    auteur    text NOT NULL,
    actif     boolean NOT NULL,
    cree_le   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX valeurs_locales_courantes ON valeurs_locales (equipe_id, parametre, id DESC);

-- Journal en ajout seul : la décision courante est la dernière ligne par alternative.
CREATE TABLE decisions (
    id          bigserial PRIMARY KEY,
    equipe_id   text NOT NULL REFERENCES equipes (id) ON DELETE CASCADE,
    alternative text NOT NULL,
    statut      text NOT NULL CHECK (statut IN ('retenue', 'a_discuter', 'aucune')),
    auteur      text NOT NULL,
    commentaire text,
    cree_le     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX decisions_courantes ON decisions (equipe_id, alternative, id DESC);

CREATE TABLE conversations (
    id        text PRIMARY KEY,
    equipe_id text NOT NULL REFERENCES equipes (id) ON DELETE CASCADE,
    donnees   jsonb NOT NULL,
    cree_le   timestamptz NOT NULL DEFAULT now(),
    maj_le    timestamptz NOT NULL DEFAULT now()
);

-- Vecteurs des passages du corpus (le texte reste dans corpus/index/chunks.jsonl).
CREATE TABLE passages (
    id        text PRIMARY KEY,
    doc_id    text NOT NULL,
    theme     text,
    reuse     text,
    empreinte text NOT NULL,          -- hachage du texte : on ne recalcule que ce qui a changé
    modele    text NOT NULL,
    embedding vector(768) NOT NULL
);
CREATE INDEX passages_embedding ON passages USING hnsw (embedding vector_cosine_ops);
