import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../src/App';
import { AuthProvider } from '../src/lib/auth';

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe('the landing page', () => {
  beforeEach(() => window.localStorage.clear());

  it('is what a signed-out visitor sees at /', () => {
    renderAt('/');
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/Your lab report, read carefully/);
  });

  it('"Get started" opens the sign-in screen ready to create an account', () => {
    renderAt('/');
    fireEvent.click(screen.getByRole('link', { name: 'Get started' }));
    expect(screen.getByRole('heading', { name: 'Create an account' })).toBeTruthy();
  });

  it.each(['Create an account'])('every "%s" button opens registration', (name) => {
    const { unmount } = renderAt('/');
    const count = screen.getAllByRole('link', { name: new RegExp(name) }).length;
    unmount();
    expect(count).toBeGreaterThanOrEqual(3);
    for (let i = 0; i < count; i += 1) {
      const view = renderAt('/');
      fireEvent.click(screen.getAllByRole('link', { name: new RegExp(name) })[i]);
      expect(screen.getByRole('heading', { name: 'Create an account' })).toBeTruthy();
      view.unmount();
    }
  });

  it('every "Sign in" link opens the sign-in form', () => {
    const { unmount } = renderAt('/');
    const count = screen.getAllByRole('link', { name: 'Sign in' }).length;
    unmount();
    expect(count).toBeGreaterThanOrEqual(3);
    for (let i = 0; i < count; i += 1) {
      const view = renderAt('/');
      fireEvent.click(screen.getAllByRole('link', { name: 'Sign in' })[i]);
      expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy();
      view.unmount();
    }
  });

  it('the wordmark on the sign-in screen leads back to the landing page', () => {
    renderAt('/signin');
    fireEvent.click(screen.getByRole('link', { name: /Vaidya/ }));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/Your lab report/);
  });
});

describe('the landing page while signed in', () => {
  const ok = (data) => ({ ok: true, status: 200, json: async () => ({ success: true, data }) });

  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('vaidyaai.refresh', 'stored-refresh-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        if (url.endsWith('/auth/refresh')) return ok({ accessToken: 'a', refreshToken: 'r' });
        if (url.endsWith('/auth/me')) return ok({ user: { id: 'u1', name: 'Asha', email: 'asha@example.com' } });
        return ok({ reports: [], profile: null });
      })
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('stays on the front page, with "Go to my reports" and no sign-in buttons', async () => {
    renderAt('/');
    const goes = await screen.findAllByRole('link', { name: /Go to my reports/ });
    expect(goes.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/Your lab report, read carefully/);
    expect(screen.queryByRole('link', { name: 'Sign in' })).toBeNull();
    expect(screen.queryByRole('link', { name: /Create an account/ })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Get started' })).toBeNull();
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull();
  });

  it('"Go to my reports" opens the Reports page with the menu', async () => {
    renderAt('/');
    fireEvent.click((await screen.findAllByRole('link', { name: /Go to my reports/ }))[0]);
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeTruthy();
    expect(screen.queryByRole('heading', { level: 1, name: /Your lab report, read carefully/ })).toBeNull();
  });
});
