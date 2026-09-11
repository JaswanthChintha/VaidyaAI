/**
 * The theme, held in exactly one place.
 *
 * design.md ships no in-app toggle and sets `data-theme` once at boot. A
 * toggle was asked for, and it is added WITHOUT giving any component
 * knowledge of the theme -- which was the spec's actual property, and the
 * reason the whole palette is tokens. Nothing here is imported by a page; the
 * only consumer is the one button in the header.
 *
 * WHY `localStorage` READS AND WRITES ARE WRAPPED. In a private window, with
 * site data blocked, or inside a test environment, the accessor itself
 * throws -- not returns null. An unguarded read at module scope would take
 * the entire app down before first paint, and a theme preference is the last
 * thing that should be able to do that.
 */

const KEY = 'vaidyaai-theme';

export const THEMES = ['light', 'dark'];

/** What the operating system asks for. Falls back to light where unknowable. */
export function systemTheme() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

/**
 * The stored CHOICE, or null when the reader has never made one.
 *
 * Null is a real state and is kept as one: "never chosen" means the app
 * follows the system, and collapsing it to 'light' would silently opt a
 * dark-mode user out of their own setting.
 */
export function storedTheme() {
  try {
    const value = localStorage.getItem(KEY);
    return THEMES.includes(value) ? value : null;
  } catch {
    return null;
  }
}

/** The theme in force: an explicit choice if there is one, else the system's. */
export function currentTheme() {
  return storedTheme() || systemTheme();
}

/** Stamp `data-theme` on <html>. Every token block keys off this attribute. */
export function applyTheme(theme = currentTheme()) {
  const next = THEMES.includes(theme) ? theme : 'light';
  document.documentElement.dataset.theme = next;
  return next;
}

/** Persist a choice and apply it. */
export function setTheme(theme) {
  const next = THEMES.includes(theme) ? theme : 'light';
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* Unwritable storage is not a reason to refuse the change for this page. */
  }
  return applyTheme(next);
}

export function toggleTheme() {
  return setTheme(currentTheme() === 'dark' ? 'light' : 'dark');
}

/**
 * Follow the system while the reader has expressed no preference of their own.
 *
 * Once they have chosen, their choice wins and the system is ignored -- a
 * toggle that got silently undone at sunset would be worse than no toggle.
 * Returns an unsubscribe function.
 */
export function watchSystemTheme() {
  try {
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (storedTheme() === null) applyTheme(systemTheme());
    };
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  } catch {
    return () => {};
  }
}
