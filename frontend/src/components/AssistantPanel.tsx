"use client";

import { useEffect, useRef, useState } from "react";
import { api, ErreurApi } from "@/lib/api";
import type { ReponseAssistant } from "@/lib/types";
import { Markdown } from "./Markdown";

type Message = { role: "user"; texte: string } | { role: "bot"; reponse: ReponseAssistant } | { role: "erreur"; texte: string };

type Props = {
  retenues: string[];
  question: { texte: string; n: number } | null;
  open: boolean;
  onClose: () => void;
};

const SUGGESTIONS = [
  "Quelles étapes pèsent le plus, et que puis-je changer sans risque pour le patient ?",
  "Explique le calcul du bloc opératoire",
  "Quelles preuves pour l'anesthésie locale ?",
  "Prépare la fiche HAS avec les options retenues",
];

export function AssistantPanel({ retenues, question, open, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [saisie, setSaisie] = useState("");
  const [enCours, setEnCours] = useState(false);
  const [conversation, setConversation] = useState<string | null>(null);
  const fin = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fin.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, enCours]);

  async function envoyer(texte: string) {
    const q = texte.trim();
    if (!q || enCours) return;
    setSaisie("");
    setMessages((m) => [...m, { role: "user", texte: q }]);
    setEnCours(true);
    try {
      const r = await api.assistant(q, conversation, retenues);
      setConversation(r.conversation_id);
      setMessages((m) => [...m, { role: "bot", reponse: r }]);
    } catch (e) {
      const msg =
        e instanceof ErreurApi && e.status === 503
          ? `${e.message} L'assistant est indisponible, mais le calcul, les options et la fiche fonctionnent sans lui.`
          : (e as Error).message;
      setMessages((m) => [...m, { role: "erreur", texte: msg }]);
    } finally {
      setEnCours(false);
    }
  }

  // Question envoyée depuis un autre écran (« Demander à l'assistant »)
  useEffect(() => {
    if (question) void envoyer(question.texte);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question?.n]);

  return (
    <aside className={`panel${open ? " open" : ""}`} aria-label="Assistant Hippo">
      <div className="panel-head">
        <div>
          <h2>Assistant Hippo</h2>
          <p>Contexte : cure de hernie inguinale</p>
        </div>
        <button
          type="button"
          className="icon-btn"
          aria-label="Nouvelle conversation"
          title="Nouvelle conversation"
          onClick={() => {
            setMessages([]);
            setConversation(null);
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
        <button type="button" className="icon-btn panel-toggle" aria-label="Fermer l'assistant" onClick={onClose}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>

      <div className="messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="empty-chat">
            <p>Posez une question sur le parcours : impact d&apos;une étape, alternatives, preuves, ou préparation de la fiche HAS.</p>
            <p>Chaque chiffre vient du moteur de calcul et chaque affirmation est sourcée.</p>
          </div>
        )}
        {messages.map((m, i) => {
          if (m.role === "user")
            return (
              <div key={i} className="msg-user">
                {m.texte}
              </div>
            );
          if (m.role === "erreur")
            return (
              <div key={i} className="msg-note" role="alert">
                {m.texte}
              </div>
            );
          const r = m.reponse;
          return (
            <div key={i} className="msg-bot">
              {r.statut !== "ok" && <div className="msg-note">{r.statut === "bloquee" ? "Réponse bloquée par le contrôle des sources." : `Réponse ${r.statut}.`}</div>}
              <Markdown texte={r.reponse} />
              {r.fiche_url && (
                <a className="btn outline small" href={r.fiche_url} target="_blank" rel="noreferrer" style={{ alignSelf: "flex-start" }}>
                  Ouvrir la fiche action HAS
                </a>
              )}
              {r.references.length > 0 && (
                <ol className="refs">
                  {r.references.map((ref) => (
                    <li key={ref.numero} id={`ref-${ref.numero}`}>
                      [{ref.numero}]{" "}
                      {ref.url ? (
                        <a href={ref.url} target="_blank" rel="noreferrer">
                          {ref.citation}
                        </a>
                      ) : (
                        ref.citation
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          );
        })}
        {enCours && <div className="typing">Hippo consulte le moteur de calcul et les sources…</div>}
        <div ref={fin} />
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          void envoyer(saisie);
        }}
      >
        <div className="chips">
          {SUGGESTIONS.slice(messages.length ? 1 : 0).map((s) => (
            <button key={s} type="button" className="chip" onClick={() => void envoyer(s)} disabled={enCours}>
              {s.length > 42 ? `${s.slice(0, 40)}…` : s}
            </button>
          ))}
        </div>
        <div className="input-row">
          <label htmlFor="question" className="visually-hidden">
            Votre question
          </label>
          <input id="question" value={saisie} onChange={(e) => setSaisie(e.target.value)} placeholder="Posez une question…" autoComplete="off" />
          <button type="submit" className="send" aria-label="Envoyer" disabled={enCours || !saisie.trim()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 12 20 4l-6 16-3-7z" />
            </svg>
          </button>
        </div>
        <p className="disclaimer">Hippo cite ses sources. Les décisions cliniques restent à l&apos;équipe soignante.</p>
      </form>
    </aside>
  );
}
