import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { api, ApiError } from '../src/lib/api';
import { AuthProvider } from '../src/lib/auth';
import AccountSettings from '../src/components/AccountSettings';

function renderAccount() {
  return render(
    <MemoryRouter initialEntries={['/profile']}>
      <AuthProvider>
        <Routes>
          <Route path="/profile" element={<AccountSettings />} />
          <Route path="/" element={<p>landing page</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

const type = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

afterEach(() => vi.restoreAllMocks());

describe('change password', () => {
  it('catches a mismatched confirmation without calling the server', async () => {
    const spy = vi.spyOn(api, 'changePassword');
    renderAccount();
    type('Current password', 'Str0ng!Passw0rd');
    type('New password', 'N3w!Passw0rd-ok');
    type('Confirm new password', 'N3w!Passw0rd-no');
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('do not match');
    expect(spy).not.toHaveBeenCalled();
  });

  it('sends the current and new password, then says it is done and clears the fields', async () => {
    const spy = vi
      .spyOn(api, 'changePassword')
      .mockResolvedValue({ accessToken: 'a', refreshToken: 'r', user: { id: '1' } });
    renderAccount();
    type('Current password', 'Str0ng!Passw0rd');
    type('New password', 'N3w!Passw0rd-ok');
    type('Confirm new password', 'N3w!Passw0rd-ok');
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Your password has been changed');
    expect(spy).toHaveBeenCalledWith('Str0ng!Passw0rd', 'N3w!Passw0rd-ok');
    expect(screen.getByLabelText('Current password')).toHaveValue('');
  });

  it('shows the server\'s own message when the current password is wrong', async () => {
    vi.spyOn(api, 'changePassword').mockRejectedValue(
      new ApiError(400, 'INVALID_CURRENT_PASSWORD', 'Your current password is not correct')
    );
    renderAccount();
    type('Current password', 'nope');
    type('New password', 'N3w!Passw0rd-ok');
    type('Confirm new password', 'N3w!Passw0rd-ok');
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Your current password is not correct');
  });
});

describe('delete account', () => {
  it('is behind a first click, and the final button waits for the password and the tick', () => {
    renderAccount();
    expect(screen.queryByLabelText('Enter your password to confirm')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Delete my account/ }));

    const final = screen.getByRole('button', { name: 'Delete my account permanently' });
    expect(final).toBeDisabled();
    type('Enter your password to confirm', 'Str0ng!Passw0rd');
    expect(final).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(final).not.toBeDisabled();
  });

  it('deletes with the password and goes to the landing page', async () => {
    const spy = vi.spyOn(api, 'deleteAccount').mockResolvedValue({ deleted: true });
    renderAccount();
    fireEvent.click(screen.getByRole('button', { name: /Delete my account/ }));
    type('Enter your password to confirm', 'Str0ng!Passw0rd');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Delete my account permanently' }));
    await waitFor(() => expect(screen.getByText('landing page')).toBeTruthy());
    expect(spy).toHaveBeenCalledWith('Str0ng!Passw0rd');
  });

  it('stays put and shows why when the password is wrong', async () => {
    vi.spyOn(api, 'deleteAccount').mockRejectedValue(
      new ApiError(400, 'INVALID_CURRENT_PASSWORD', 'Your password is not correct')
    );
    renderAccount();
    fireEvent.click(screen.getByRole('button', { name: /Delete my account/ }));
    type('Enter your password to confirm', 'wrong');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Delete my account permanently' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Your password is not correct');
    expect(screen.queryByText('landing page')).toBeNull();
  });

  it('"Keep my account" closes it again', () => {
    renderAccount();
    fireEvent.click(screen.getByRole('button', { name: /Delete my account/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Keep my account' }));
    expect(screen.queryByLabelText('Enter your password to confirm')).toBeNull();
  });
});
