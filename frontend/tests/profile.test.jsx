import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Profile, { answerLabel } from '../src/pages/Profile';
import { api } from '../src/lib/api';
import { AuthProvider } from '../src/lib/auth';


function mount(profile) {
  vi.spyOn(api, 'getProfile').mockResolvedValue(
    profile === undefined ? { profile: {} } : { profile }
  );
  vi.spyOn(api, 'saveProfile').mockImplementation(async (body) => ({
    profile: { ...profile, ...body, completeness: profile?.completeness },
  }));
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Profile />
      </AuthProvider>
    </MemoryRouter>
  );
}

const group = (questionText) =>
  [...document.querySelectorAll('details.tristate')].find((f) =>
    f.querySelector('.tristate__q').textContent.includes(questionText)
  );

const chosen = (questionText) => {
  const radios = [...group(questionText).querySelectorAll('input[type=radio]')];
  return ['Yes', 'No', 'Not sure'][radios.findIndex((r) => r.checked)] ?? 'none';
};

const summaryAnswer = (questionText) =>
  group(questionText).querySelector('.tristate__answer').textContent.trim();

const save = () => document.querySelector('form.card button').click();

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('the tri-state answers', () => {
  it('shows a stored FALSE as "No", not as "Not sure"', async () => {
    mount({ age: 20, hypertension: false, heartDisease: true });

    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());
    expect(chosen('high blood pressure')).toBe('No');
    expect(chosen('heart disease')).toBe('Yes');
  });

  it('shows an ABSENT answer as "Not sure", never as "No"', async () => {
    mount({ age: 20 });

    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());
    expect(chosen('high blood pressure')).toBe('Not sure');
    expect(chosen('heart disease')).toBe('Not sure');
  });

  it('sends "Not sure" by OMITTING the key, never as null', async () => {
    mount({ age: 20, hypertension: true, heartDisease: true });
    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());

    group('high blood pressure').querySelectorAll('input[type=radio]')[2].click();
    save();

    await waitFor(() => expect(api.saveProfile).toHaveBeenCalled());
    const body = api.saveProfile.mock.calls[0][0];
    expect('hypertension' in body).toBe(false);
    expect(body.hypertension).toBeUndefined();
    expect(body.heartDisease).toBe(true);
  });

  it('sends FALSE, because "No" is a real answer', async () => {
    mount({ age: 20 });
    await waitFor(() => expect(group('heart disease')).toBeTruthy());

    group('heart disease').querySelectorAll('input[type=radio]')[1].click();
    save();

    await waitFor(() => expect(api.saveProfile).toHaveBeenCalled());
    expect(api.saveProfile.mock.calls[0][0].heartDisease).toBe(false);
  });
});

describe('what the page says after a save', () => {
  it('warns that an already-analysed report will not change', async () => {
    mount({ age: 20 });
    await waitFor(() => expect(group('heart disease')).toBeTruthy());

    expect(screen.queryByText(/next time a report is analysed/)).not.toBeInTheDocument();
    save();

    expect(
      await screen.findByText(/next time a report is analysed/)
    ).toBeInTheDocument();
    expect(screen.getByText(/do not change/)).toBeInTheDocument();
  });

  it('names a still-blank field in words, never as a document key', async () => {
    mount({
      age: 20,
      completeness: { fields: 7, filled: 6, percent: 86, missing: ['heartDisease'] },
    });

    const said = await screen.findByText(/Not answered yet/);
    expect(said.textContent).toMatch(/diagnosed heart disease/);
    expect(said.textContent).not.toMatch(/heartDisease/);
  });

  it('names several blank fields in words', async () => {
    mount({
      age: 20,
      completeness: {
        fields: 7,
        filled: 5,
        percent: 71,
        missing: ['hypertension', 'heartDisease'],
      },
    });

    const said = await screen.findByText(/Not answered yet/);
    expect(said.textContent).toMatch(/diagnosed high blood pressure/);
    expect(said.textContent).toMatch(/diagnosed heart disease/);
    expect(said.textContent).not.toMatch(/hypertension|heartDisease/);
  });
});

describe('the diagnosis questions collapse', () => {
  it('starts closed, on a profile with answers and on one without', async () => {
    mount({ age: 20, hypertension: true });
    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());
    expect(group('high blood pressure').open).toBe(false);
    expect(group('heart disease').open).toBe(false);
  });

  it('shows the recorded answer WITHOUT being opened', async () => {
    mount({ age: 20, hypertension: false, heartDisease: true });
    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());

    expect(group('high blood pressure').open).toBe(false);
    expect(summaryAnswer('high blood pressure')).toBe('No');
    expect(summaryAnswer('heart disease')).toBe('Yes');
  });

  it('shows an UNANSWERED question as unanswered on the summary', async () => {
    mount({ age: 20 });
    await waitFor(() => expect(group('heart disease')).toBeTruthy());
    expect(summaryAnswer('heart disease')).toMatch(/Not sure/);
  });

  it('closes both again after Save changes', async () => {
    mount({ age: 20 });
    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());

    const box = group('high blood pressure');
    box.open = true;
    box.dispatchEvent(new Event('toggle'));
    await waitFor(() => expect(group('high blood pressure').open).toBe(true));

    save();

    await waitFor(() => expect(api.saveProfile).toHaveBeenCalled());
    await waitFor(() => expect(group('high blood pressure').open).toBe(false));
    expect(group('heart disease').open).toBe(false);
  });

  it('does not re-open a box just because the answer is missing', async () => {
    mount({ age: 20, completeness: { fields: 7, filled: 5, percent: 71, missing: ['hypertension', 'heartDisease'] } });
    await waitFor(() => expect(group('heart disease')).toBeTruthy());

    expect(group('high blood pressure').open).toBe(false);
    expect(group('heart disease').open).toBe(false);
  });

  it('groups the radios for a screen reader without a second copy of the question', async () => {
    mount({ age: 20 });
    await waitFor(() => expect(group('heart disease')).toBeTruthy());

    const box = group('heart disease');
    const radiogroup = box.querySelector('[role="radiogroup"]');
    expect(radiogroup).not.toBeNull();
    expect(radiogroup.getAttribute('aria-label')).toBe('Diagnosed heart disease');
    expect(box.querySelector('legend')).toBeNull();
    expect(box.querySelectorAll('.tristate__q')).toHaveLength(1);
  });
});

describe('the answer label, on a value it does not recognise', () => {
  it('says the three known answers', () => {
    expect(answerLabel(true)).toBe('Yes');
    expect(answerLabel(false)).toBe('No');
    expect(answerLabel(null)).toMatch(/Not sure/);
  });

  it('never claims an answer for a value it cannot read', () => {
    for (const odd of [undefined, 'yes', 1, 0, {}]) {
      expect(answerLabel(odd), String(odd)).toMatch(/Not sure/);
      expect(answerLabel(odd), String(odd)).not.toBe('Yes');
      expect(answerLabel(odd), String(odd)).not.toBe('No');
    }
  });
});
