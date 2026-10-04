import { useEffect, useState } from 'react';

/**
 * The short intro shown over the landing page, once per visit.
 *
 * About 4.5 seconds: the leaf draws itself, the wordmark and tagline rise in,
 * a thin line fills, and the whole screen lifts away to the page underneath.
 * The landing page is already rendered beneath it, so nothing shifts when it
 * goes.
 *
 * NEVER SHOWN to someone who has asked their system for reduced motion -- an
 * intro that exists only to move has nothing to offer them -- and never twice
 * in one visit (sessionStorage), so going back to the landing page does not
 * replay it. "Skip" ends it at once.
 */
const SEEN_KEY = 'vaidyaai-intro-seen';
const LEAVE_AT_MS = 4000;
const GONE_AT_MS = 4800;

function shouldShow() {
  try {
    if (window.sessionStorage.getItem(SEEN_KEY)) return false;
  } catch {
    // Storage blocked: show it; at worst it plays again next visit.
  }
  try {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  } catch {
    // No matchMedia (old browser, test environment): fall through.
  }
  return true;
}

function remember() {
  try {
    window.sessionStorage.setItem(SEEN_KEY, '1');
  } catch {
    // Not fatal; see shouldShow.
  }
}

export default function Splash() {
  const [phase, setPhase] = useState(() => (shouldShow() ? 'showing' : 'gone'));

  useEffect(() => {
    if (phase !== 'showing') return undefined;
    remember();
    const leave = setTimeout(() => setPhase('leaving'), LEAVE_AT_MS);
    const gone = setTimeout(() => setPhase('gone'), GONE_AT_MS);
    return () => {
      clearTimeout(leave);
      clearTimeout(gone);
    };
  }, [phase]);

  useEffect(() => {
    if (phase !== 'leaving') return undefined;
    const t = setTimeout(() => setPhase('gone'), GONE_AT_MS - LEAVE_AT_MS);
    return () => clearTimeout(t);
  }, [phase]);

  if (phase === 'gone') return null;

  return (
    <div className={phase === 'leaving' ? 'splash splash--leaving' : 'splash'} aria-label="VaidyaAI">
      <div className="splash__inner">
        <svg className="splash__leaf" width="72" height="72" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path pathLength="1" d="M5 19c0-8 5-13.5 14-14-.5 9-6 14-14 14z" />
          <path pathLength="1" d="M5 19 13 11" />
        </svg>
        <p className="splash__word">
          Vaidya<em>AI</em>
        </p>
        <p className="splash__tag">Your lab report, read carefully.</p>
        <span className="splash__bar" aria-hidden="true">
          <i />
        </span>
      </div>
      <button type="button" className="link splash__skip" onClick={() => setPhase('leaving')}>
        Skip
      </button>
    </div>
  );
}
