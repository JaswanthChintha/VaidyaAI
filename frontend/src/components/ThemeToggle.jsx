import { useEffect, useState } from 'react';
import { currentTheme, toggleTheme, watchSystemTheme } from '../lib/theme';

/**
 * The one control that knows the theme exists.
 *
 * It holds the CURRENT theme only so it can label itself; the actual switch is
 * a `data-theme` attribute on <html>, which every token block already keys
 * off. No other component reads or passes a theme, which is why adding this
 * did not touch a single page.
 *
 * LABELLED WITH A WORD, NOT JUST AN ICON. A sun and a moon are ambiguous in a
 * way that matters here -- half of all users read the icon as "the mode you
 * are in" and half as "the mode you will get". The text says which, and
 * `aria-pressed` says it again for a screen reader.
 */
export default function ThemeToggle() {
  const [theme, setThemeState] = useState(() => currentTheme());

  // Follow the system until the reader chooses for themselves; `theme.js`
  // ignores the system once a choice is stored.
  useEffect(() => watchSystemTheme(), []);

  // Re-read after a system change so the label cannot drift from the truth.
  useEffect(() => {
    const sync = () => setThemeState(currentTheme());
    window.addEventListener('focus', sync);
    return () => window.removeEventListener('focus', sync);
  }, []);

  const dark = theme === 'dark';

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-pressed={dark}
      title={dark ? 'Switch to the light theme' : 'Switch to the dark theme'}
      onClick={() => setThemeState(toggleTheme())}
    >
      {dark ? (
        // Sun: switching to light.
        <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <circle cx="12" cy="12" r="4.4" fill="currentColor" />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
            <line
              key={deg}
              x1="12"
              y1="1.8"
              x2="12"
              y2="4.4"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              transform={`rotate(${deg} 12 12)`}
            />
          ))}
        </svg>
      ) : (
        // Moon: switching to dark.
        <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path
            d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1Z"
            fill="currentColor"
          />
        </svg>
      )}
      <span>{dark ? 'Light' : 'Dark'}</span>
    </button>
  );
}
