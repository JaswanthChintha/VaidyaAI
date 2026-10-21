import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import Reports from '../src/pages/Reports';
import { AuthProvider } from '../src/lib/auth';
import { api, ApiError } from '../src/lib/api';
import { joinDetails, missingKeyDetails } from '../src/lib/profileGaps';


const NOT_FOUND = () => new ApiError(404, 'NOT_FOUND', 'Profile not found');

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});
afterEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function mountReports({ profile, profileError } = {}) {
  vi.spyOn(api, 'listReports').mockResolvedValue({ reports: [] });
  const getProfile = vi.spyOn(api, 'getProfile');
  if (profileError) getProfile.mockRejectedValue(profileError);
  else getProfile.mockResolvedValue({ profile });
  return render(
    <MemoryRouter>
      <Reports />
    </MemoryRouter>
  );
}

describe('after creating an account', () => {
  it('opens Your details with the welcome note -- through the REAL router', async () => {
    vi.spyOn(api, 'register').mockResolvedValue({
      user: { id: 'u1', name: 'New User', email: 'new@example.invalid' },
      accessToken: 'a'.repeat(40),
      refreshToken: 'r'.repeat(40),
    });
    vi.spyOn(api, 'getProfile').mockRejectedValue(NOT_FOUND());
    vi.spyOn(api, 'listReports').mockResolvedValue({ reports: [] });

    render(
      <MemoryRouter initialEntries={['/signin']}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Create an account' }));
    fireEvent.change(screen.getByLabelText('Name', { exact: false }), { target: { value: 'New User' } });
    fireEvent.change(screen.getByLabelText('Email', { exact: false }), {
      target: { value: 'new@example.invalid' },
    });
    fireEvent.change(document.querySelectorAll('.auth input')[2], { target: { value: 'Sample-1a!' } });
    fireEvent.change(screen.getByLabelText('Confirm password', { exact: false }), {
      target: { value: 'Sample-1a!' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    expect(
      await screen.findByRole('heading', { name: /start with your details/ })
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Your details' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Skip for now' })).toHaveAttribute('href', '/reports');
  });

  it('a returning user who signs in still goes to Reports, with no welcome note', async () => {
    vi.spyOn(api, 'login').mockResolvedValue({
      user: { id: 'u1', name: 'Old User', email: 'old@example.invalid' },
      accessToken: 'a'.repeat(40),
      refreshToken: 'r'.repeat(40),
    });
    vi.spyOn(api, 'getProfile').mockResolvedValue({ profile: { age: 40, gender: 'female' } });
    vi.spyOn(api, 'listReports').mockResolvedValue({ reports: [] });

    render(
      <MemoryRouter initialEntries={['/signin']}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    );
    fireEvent.change(await screen.findByLabelText('Email', { exact: false }), {
      target: { value: 'old@example.invalid' },
    });
    fireEvent.change(document.querySelector('.auth__password input'), { target: { value: 'whatever' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('heading', { name: 'Your reports' })).toBeInTheDocument();
    expect(screen.queryByText(/start with your details/)).not.toBeInTheDocument();
  });
});

describe('the reminder on Reports', () => {
  it('shows when there is no profile yet, naming age and sex', async () => {
    mountReports({ profileError: NOT_FOUND() });
    expect(
      await screen.findByRole('heading', { name: 'Your profile is missing your age and sex' })
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Complete your profile' })).toHaveAttribute('href', '/profile');
  });

  it('names only what is missing', async () => {
    mountReports({ profile: { age: 52, heightCm: 170 } });
    expect(
      await screen.findByRole('heading', { name: 'Your profile is missing your sex' })
    ).toBeInTheDocument();
  });

  it('is gone once age and sex are filled in', async () => {
    const { container } = mountReports({ profile: { age: 52, gender: 'male' } });
    await screen.findByRole('heading', { name: 'Your reports' });
    await waitFor(() => expect(api.getProfile).toHaveBeenCalled());
    expect(container.querySelector('.profile-nudge')).toBeNull();
  });

  it('"Prefer not to say" is an answer, not a gap -- no nagging', async () => {
    const { container } = mountReports({ profile: { age: 30, gender: 'prefer_not_to_say' } });
    await waitFor(() => expect(api.getProfile).toHaveBeenCalled());
    await screen.findByRole('heading', { name: 'Your reports' });
    expect(container.querySelector('.profile-nudge')).toBeNull();
  });

  it('says nothing when the profile could not be fetched -- unknown is not "empty"', async () => {
    const { container } = mountReports({ profileError: new ApiError(500, 'INTERNAL', 'Server error') });
    await waitFor(() => expect(api.getProfile).toHaveBeenCalled());
    await screen.findByRole('heading', { name: 'Your reports' });
    expect(container.querySelector('.profile-nudge')).toBeNull();
  });

  it('never blocks: the upload form is there either way', async () => {
    mountReports({ profileError: NOT_FOUND() });
    await screen.findByRole('heading', { name: /missing your age and sex/ });
    expect(screen.getByRole('heading', { name: 'Upload a report' })).toBeInTheDocument();
  });
});

describe('missingKeyDetails / joinDetails', () => {
  it.each([
    [null, ['age', 'sex']],
    [{}, ['age', 'sex']],
    [{ age: 0, gender: 'female' }, []],
    [{ age: '', gender: null }, ['age', 'sex']],
    [{ gender: 'other' }, ['age']],
  ])('%j -> %j', (profile, expected) => {
    expect(missingKeyDetails(profile)).toEqual(expected);
  });

  it('joins in plain English', () => {
    expect(joinDetails(['age'])).toBe('age');
    expect(joinDetails(['age', 'sex'])).toBe('age and sex');
  });
});
