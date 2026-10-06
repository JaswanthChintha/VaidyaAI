import { useEffect, useRef, useState } from 'react';

/**
 * 🔊 READ ALOUD (2026-10-06).
 *
 * THE BROWSER SPEAKS, NOT THE SERVER. The Web Speech API runs on the reader's
 * own device: no Gemini call, no server work, nothing to deploy. It works the
 * same on localhost and on a public site.
 *
 * ON-DEVICE VOICES FIRST. Some browsers offer "online" voices that send the
 * text to Microsoft or Google to be spoken. For a medical explanation the
 * voice that runs on the device (`localService`) is preferred, and an online
 * one is used only when the device has nothing else for that language.
 *
 * NO VOICE, NO BUTTON. Where speech is not supported, or the device has no
 * voice for the language, the button is not shown -- never an English voice
 * reading another language. `lang` is ready for Hindi ('hi') and Telugu
 * ('te') once translated text exists.
 *
 * ONE AT A TIME. Starting one stops any other; leaving the page stops it.
 */

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
    // On-device first, then the preferred region order, then anything.
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

  // Voices arrive asynchronously in most browsers.
  useEffect(() => {
    if (!speechAvailable()) return undefined;
    const synth = window.speechSynthesis;
    const update = () => setVoice(pickVoice(synth.getVoices(), lang));
    update();
    synth.addEventListener?.('voiceschanged', update);
    return () => synth.removeEventListener?.('voiceschanged', update);
  }, [lang]);

  // Leaving the page stops THIS reading (not someone else's).
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
    synth.cancel(); // one at a time
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
