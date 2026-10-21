const KEY = 'vaidyaai-theme';

export const THEMES = ['light', 'dark'];

export function systemTheme() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function storedTheme() {
  try {
    const value = localStorage.getItem(KEY);
    return THEMES.includes(value) ? value : null;
  } catch {
    return null;
  }
}

export function currentTheme() {
  return storedTheme() || systemTheme();
}

export function applyTheme(theme = currentTheme()) {
  const next = THEMES.includes(theme) ? theme : 'light';
  document.documentElement.dataset.theme = next;
  return next;
}

export function setTheme(theme) {
  const next = THEMES.includes(theme) ? theme : 'light';
  try {
    localStorage.setItem(KEY, next);
  } catch {
  }
  return applyTheme(next);
}

export function toggleTheme() {
  return setTheme(currentTheme() === 'dark' ? 'light' : 'dark');
}

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
