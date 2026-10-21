import { useEffect, useState } from 'react';
import { LOGO_DROP, LOGO_PULSE } from './Logo';

const SEEN_KEY = 'vaidyaai-intro-seen';
const LEAVE_AT_MS = 4000;
const GONE_AT_MS = 4800;

export const SPLASH_COVER_MS = 4400;

export function shouldShow() {
  try {
    if (window.sessionStorage.getItem(SEEN_KEY)) return false;
  } catch {
  }
  try {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  } catch {
  }
  return true;
}

function remember() {
  try {
    window.sessionStorage.setItem(SEEN_KEY, '1');
  } catch {
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
        <svg className="splash__logo" width="88" height="88" viewBox="0 0 48 48" aria-hidden="true">
          <rect className="splash__tile" width="48" height="48" rx="13" />
          <path className="splash__drop" pathLength="1" d={LOGO_DROP} />
          <path className="splash__pulse" pathLength="1" d={LOGO_PULSE} />
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
