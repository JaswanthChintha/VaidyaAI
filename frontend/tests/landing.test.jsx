import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../src/App';
import { AuthProvider } from '../src/lib/auth';

/**
 * The landing page's buttons, clicked through the REAL app while signed out
 * (2026-10-02). Each must reach the sign-in screen, and the "create" ones
 * must arrive with the registration form already showing.
 */
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
