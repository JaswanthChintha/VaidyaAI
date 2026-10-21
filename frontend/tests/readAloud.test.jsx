import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ReadAloud, { pickVoice } from '../src/components/ReadAloud';


const VOICES = [
  { name: 'Online US', lang: 'en-US', localService: false },
  { name: 'Device GB', lang: 'en-GB', localService: true },
  { name: 'Device IN', lang: 'en-IN', localService: true },
  { name: 'Device Hindi', lang: 'hi-IN', localService: true },
];

function installSpeech(voices = VOICES) {
  const synth = {
    speak: vi.fn(),
    cancel: vi.fn(),
    getVoices: () => voices,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  class Utterance {
    constructor(text) {
      this.text = text;
    }
  }
  vi.stubGlobal('speechSynthesis', synth);
  vi.stubGlobal('SpeechSynthesisUtterance', Utterance);
  window.speechSynthesis = synth;
  window.SpeechSynthesisUtterance = Utterance;
  return synth;
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.speechSynthesis;
  delete window.SpeechSynthesisUtterance;
});

describe('choosing a voice', () => {
  it('prefers an on-device voice, then the Indian English one', () => {
    expect(pickVoice(VOICES, 'en').name).toBe('Device IN');
  });

  it('uses an online voice only when nothing on the device speaks the language', () => {
    expect(pickVoice([VOICES[0]], 'en').name).toBe('Online US');
  });

  it('finds Hindi, and finds nothing for a language with no voice', () => {
    expect(pickVoice(VOICES, 'hi').name).toBe('Device Hindi');
    expect(pickVoice(VOICES, 'te')).toBeNull();
  });
});

describe('the button', () => {
  beforeEach(() => {
    window.speechSynthesis = undefined;
  });

  it('is not shown where the browser cannot speak', () => {
    delete window.speechSynthesis;
    render(<ReadAloud text="Haemoglobin. It carries oxygen." />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('is not shown when the device has no voice for the language', () => {
    installSpeech();
    render(<ReadAloud text="Telugu text" lang="te" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('reads exactly the text it was given, with the chosen voice, then offers Stop', () => {
    const synth = installSpeech();
    render(<ReadAloud text="Haemoglobin. It carries oxygen." label="Haemoglobin" />);

    fireEvent.click(screen.getByRole('button', { name: 'Read aloud: Haemoglobin' }));
    expect(synth.cancel).toHaveBeenCalled();
    expect(synth.speak).toHaveBeenCalledTimes(1);
    const utterance = synth.speak.mock.calls[0][0];
    expect(utterance.text).toBe('Haemoglobin. It carries oxygen.');
    expect(utterance.voice.name).toBe('Device IN');

    const stop = screen.getByRole('button', { name: 'Stop reading' });
    expect(stop).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(stop);
    expect(synth.cancel).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: 'Read aloud: Haemoglobin' })).toBeInTheDocument();
  });

  it('goes back to "Read aloud" when the speech ends by itself', () => {
    const synth = installSpeech();
    render(<ReadAloud text="Short." />);
    fireEvent.click(screen.getByRole('button', { name: 'Read aloud' }));
    const utterance = synth.speak.mock.calls[0][0];
    act(() => utterance.onend());
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeInTheDocument();
  });

  it('stops its own reading when the page is left', () => {
    const synth = installSpeech();
    const { unmount } = render(<ReadAloud text="Short." />);
    fireEvent.click(screen.getByRole('button', { name: 'Read aloud' }));
    const before = synth.cancel.mock.calls.length;
    unmount();
    expect(synth.cancel.mock.calls.length).toBe(before + 1);
  });
});
