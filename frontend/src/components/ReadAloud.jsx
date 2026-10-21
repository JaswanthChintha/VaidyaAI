import { useEffect, useRef, useState } from 'react';


const PREFERRED_REGION = { en: ['en-IN', 'en-GB', 'en-US'], hi: ['hi-IN'], te: ['te-IN'] };

export function pickVoice(voices, lang) {
  const matching = (voices || []).filter((v) =>
    String(v.lang || '').toLowerCase().replace('_', '-').startsWith(lang.toLowerCase())
  );
  if (!matching.length) return null;
  const regions = PREFERRED_REGION[lang] || [];
  const rank = (v) => {
    const region = regions.findIndex(
      (r) => String(v.lang).toLowerCase().replace('_', '-') === r.toLowerCase()
    );
    return (v.localService ? 0 : 100) + (region === -1 ? 50 : region);
  };
  return [...matching].sort((a, b) => rank(a) - rank(b))[0];
}

function speechAvailable() {
  return (
    typeof window !== 'undefined'
    && 'speechSynthesis' in window
    && typeof window.SpeechSynthesisUtterance === 'function'
  );
}

export default function ReadAloud({ text, lang = 'en', label }) {
  const [voice, setVoice] = useState(null);
  const [speaking, setSpeaking] = useState(false);
  const mine = useRef(null);

  useEffect(() => {
    if (!speechAvailable()) return undefined;
    const synth = window.speechSynthesis;
    const update = () => setVoice(pickVoice(synth.getVoices(), lang));
    update();
    synth.addEventListener?.('voiceschanged', update);
    return () => synth.removeEventListener?.('voiceschanged', update);
  }, [lang]);

  useEffect(
    () => () => {
      if (mine.current && speechAvailable()) window.speechSynthesis.cancel();
    },
    []
  );

  if (!speechAvailable() || !voice || !text || !String(text).trim()) return null;

  function toggle() {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    synth.cancel();
    const utterance = new window.SpeechSynthesisUtterance(String(text));
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.95;
    const done = () => {
      if (mine.current === utterance) mine.current = null;
      setSpeaking(false);
    };
    utterance.onend = done;
    utterance.onerror = done;
    mine.current = utterance;
    setSpeaking(true);
    synth.speak(utterance);
  }

  return (
    <button
      type="button"
      className="link read-aloud"
      onClick={toggle}
      aria-pressed={speaking}
      aria-label={speaking ? 'Stop reading' : `Read aloud${label ? `: ${label}` : ''}`}
    >
      <span aria-hidden="true">{speaking ? '■' : '🔊'}</span>{' '}
      {speaking ? 'Stop' : 'Read aloud'}
    </button>
  );
}
