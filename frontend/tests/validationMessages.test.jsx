import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthProvider } from '../src/lib/auth';
import { api, ApiError } from '../src/lib/api';

/**
 * A form the backend refuses says WHICH box was wrong (owner, 2026-10-10).
 *
 * Creating an account with a weak password showed only "Invalid request
 * payload" -- the backend's general line -- while the actual reason sat
 * unread in `error.details`. The body below is the backend's real shape
 * (middleware/validate.js).
 */

const PASSWORD_RULE =
  'Password must be at least 8 characters and include an uppercase letter, a lowercase letter, a number and a special character';

const refused = (details) => ({
  ok: false,
  status: 422,
  json: async () => ({
    success: false,
    error: { code: 'VALIDATION_ERROR', message: 'Invalid request payload', details },
  }),
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('a refused form', () => {
  it("carries the backend's reason, not the general line", async () => {
    vi.stubGlobal('fetch', vi.fn(async () => refused([{ field: 'password', message: PASSWORD_RULE }])));
    const error = await api.register({ name: 'A', email: 'a@example.com', password: 'weak' }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.code).toBe('VALIDATION_ERROR');
    expect(error.message).toBe(`${PASSWORD_RULE}.`);
    expect(error.details).toEqual([{ field: 'password', message: PASSWORD_RULE }]);
  });

  it('shows each different reason once, in order', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        refused([
          { field: 'email', message: 'Please provide a valid email address' },
          { field: 'password', message: PASSWORD_RULE },
          { field: 'newPassword', message: PASSWORD_RULE },
        ])
      )
    );
    const error = await api.register({}).catch((e) => e);
    expect(error.message).toBe(`Please provide a valid email address. ${PASSWORD_RULE}.`);
  });

  it('keeps the general line when there is no reason to show', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => refused([])));
    const error = await api.register({}).catch((e) => e);
    expect(error.message).toBe('Invalid request payload');
  });

  it('leaves every other error exactly as the backend wrote it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 409,
        json: async () => ({
          success: false,
          error: { code: 'CONFLICT', message: 'An account with that email already exists' },
        }),
      }))
    );
    const error = await api.register({}).catch((e) => e);
    expect(error.message).toBe('An account with that email already exists');
    expect(error.details).toEqual([]);
  });
});

describe('creating an account with a weak password', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal('fetch', vi.fn(async () => refused([{ field: 'password', message: PASSWORD_RULE }])));
  });

  it('says what is wrong with the password, not "Invalid request payload"', async () => {
    render(
      <MemoryRouter initialEntries={[{ pathname: '/signin', state: { mode: 'register' } }]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Prajju' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'prajju@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'weakpassword12' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'weakpassword12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('include an uppercase letter, a lowercase letter, a number and a special character');
    expect(alert).not.toHaveTextContent('Invalid request payload');
  });
});
