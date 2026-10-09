import { useEffect, useRef, useState } from 'react';
import { useMatch } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import Icon from './Icon';

/**
 * The VaidyaAI chatbot (owner, 2026-10-09).
 *
 * A bubble on every signed-in page. It answers questions about using the
 * app, general lab-test and health questions, and -- on a report's own pages
 * -- questions about that report. The answers come from free OpenRouter
 * models through the ai-service, behind the same safety checker as every
 * other written explanation; Gemini is never used for chat.
 *
 * NOTHING IS STORED: the conversation lives in this component and is gone on
 * reload. It is cleared when the reader moves to a different report, so an
 * answer about one report never sits above a question about another.
 */

export const MAX_QUESTION_CHARS = 300;

export const GENERAL_SUGGESTIONS = [
  'How do I upload a report?',
  "What does 'Not assessed' mean?",
  'What is the Timeline page?',
  'What is HbA1c?',
];

export const REPORT_SUGGESTIONS = [
  'Explain my results in simple words',
  'Which of my results are outside the usual range?',
  'What could I ask my doctor about this report?',
];

const SOURCE_KIND = { report: 'This report', app_help: 'VaidyaAI help', knowledge: 'Reviewed reference' };

function errorText(err) {
  if (err instanceof ApiError && err.status === 429) {
    return "You've asked a lot of questions in a short time. Please wait a while and try again.";
  }
  if (err instanceof ApiError && err.status === 422) {
    return `Please type a question of up to ${MAX_QUESTION_CHARS} characters.`;
  }
  return "Chat isn't available right now. Please try again later.";
}

export default function ChatBot() {
  // A report's own pages: /reports/:id, /reports/:id/doctor-summary, ...
  const match = useMatch({ path: '/reports/:id/*', end: false });
  const reportId = match?.params?.id && /^[a-f0-9]{24}$/i.test(match.params.id) ? match.params.id : null;

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  // A different report, a fresh conversation.
  useEffect(() => {
    setMessages([]);
  }, [reportId]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    const list = listRef.current;
    if (list && typeof list.scrollTo === 'function') list.scrollTo({ top: list.scrollHeight });
  }, [messages, busy]);

  async function send(text) {
    const question = (text ?? draft).trim().slice(0, MAX_QUESTION_CHARS);
    if (!question || busy) return;
    setDraft('');
    setMessages((m) => [...m, { role: 'user', text: question }]);
    setBusy(true);
    try {
      const data = await api.chat(question, reportId);
      const chat = data.chat || {};
      setMessages((m) => [
        ...m,
        { role: 'bot', text: chat.answer, outcome: chat.outcome, sources: chat.sources || [] },
      ]);
    } catch (err) {
      setMessages((m) => [...m, { role: 'bot', text: errorText(err), outcome: 'error', sources: [] }]);
    } finally {
      setBusy(false);
    }
  }

  const suggestions = reportId ? [...REPORT_SUGGESTIONS, ...GENERAL_SUGGESTIONS.slice(0, 2)] : GENERAL_SUGGESTIONS;

  if (!open) {
    return (
      <button type="button" className="chatbot__bubble" onClick={() => setOpen(true)} aria-label="Open chat">
        <Icon name="chat" size={24} />
      </button>
    );
  }

  return (
    <section
      className="chatbot"
      role="dialog"
      aria-label="Ask VaidyaAI"
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false);
      }}
    >
      <header className="chatbot__head">
        <span className="chatbot__title">
          <Icon name="chat" size={18} />
          Ask VaidyaAI
        </span>
        <button type="button" className="chatbot__close" onClick={() => setOpen(false)} aria-label="Close chat">
          <Icon name="close" size={18} />
        </button>
      </header>

      <div className="chatbot__list" ref={listRef} aria-live="polite">
        {messages.length === 0 ? (
          <div className="chatbot__intro">
            <p>
              {reportId
                ? 'Ask about this report, your lab tests, or how to use VaidyaAI.'
                : 'Ask about lab tests, general health, or how to use VaidyaAI.'}
            </p>
            <div className="chatbot__suggestions">
              {suggestions.map((s) => (
                <button key={s} type="button" className="chatbot__chip" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            // eslint-disable-next-line react/no-array-index-key
            <div key={i} className={`chatbot__msg chatbot__msg--${m.role}`}>
              <p>{m.text}</p>
              {m.role === 'bot' && m.sources?.length ? (
                <p className="chatbot__sources">
                  From: {m.sources.map((s) => `${SOURCE_KIND[s.kind] || 'Source'} – ${s.title}`).join('; ')}
                </p>
              ) : null}
            </div>
          ))
        )}
        {busy ? <p className="chatbot__thinking">Thinking…</p> : null}
      </div>

      <form
        className="chatbot__form"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <label className="visually-hidden" htmlFor="chatbot-input">
          Your question
        </label>
        <input
          id="chatbot-input"
          ref={inputRef}
          value={draft}
          maxLength={MAX_QUESTION_CHARS}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a question…"
          autoComplete="off"
        />
        <button type="submit" className="chatbot__send" disabled={busy || !draft.trim()} aria-label="Send">
          <Icon name="send" size={18} />
        </button>
      </form>
      <p className="chatbot__note">
        General information, not medical advice.
        {reportId ? " Your question and this report's results" : ' Your question'} are sent to an outside AI
        service to write the answer.
      </p>
    </section>
  );
}
