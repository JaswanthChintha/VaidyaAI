import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Profile, { answerLabel } from '../src/pages/Profile';
import { api } from '../src/lib/api';
import { AuthProvider } from '../src/lib/auth';

/**
 * THE PROFILE FORM, WHICH HAD NO TESTS AT ALL.
 *
 * It carries the two answers the heart model names as its single biggest
 * limitation -- "no value was available for your history of heart disease and
 * history of high blood pressure" is on the dashboard because of this page --
 * and the file's own comments state three guarantees that nothing checked:
 *
 *   1. a stored `false` round-trips as "No", never as "Not sure";
 *   2. "Not sure" is sent by OMITTING the key, because the validator rejects
 *      an explicit null with a 422 the patient cannot act on;
 *   3. `false` IS sent, because it is a real answer.
 *
 * A comment asserting a guarantee is not a guarantee -- this project has
 * found four false ones. These are the tests.
 */

function mount(profile) {
  vi.spyOn(api, 'getProfile').mockResolvedValue(
    profile === undefined ? { profile: {} } : { profile }
  );
  vi.spyOn(api, 'saveProfile').mockImplementation(async (body) => ({
    profile: { ...profile, ...body, completeness: profile?.completeness },
  }));
  // AuthProvider since 2026-10-02: the page now carries the account section
  // (change password, delete account), which needs the session context it
  // always has in the real app.
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

/** What the reader sees WITHOUT opening the box. */
const summaryAnswer = (questionText) =>
  group(questionText).querySelector('.tristate__answer').textContent.trim();

const save = () => document.querySelector('form.card button').click();

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('the tri-state answers', () => {
  it('shows a stored FALSE as "No", not as "Not sure"', async () => {
    // `?? null` and not `|| false`. The inverse mistake -- reading a stored
    // `false` as unknown -- would tell a patient the platform never asked,
    // and would quietly re-ask a question they already answered.
    mount({ age: 20, hypertension: false, heartDisease: true });

    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());
    expect(chosen('high blood pressure')).toBe('No');
    expect(chosen('heart disease')).toBe('Yes');
  });

  it('shows an ABSENT answer as "Not sure", never as "No"', async () => {
    // The whole reason the control is tri-state. An unanswered question
    // rendering as "No" is an absence turned into a value -- this codebase's
    // most repeated hazard, on the page where it would originate.
    mount({ age: 20 });

    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());
    expect(chosen('high blood pressure')).toBe('Not sure');
    expect(chosen('heart disease')).toBe('Not sure');
  });

  it('sends "Not sure" by OMITTING the key, never as null', async () => {
    // The validator rejects an explicit null outright ("Heart disease status
    // must be true or false"), so sending one would 422 a patient for
    // choosing an option the form offers them. PUT's replace semantics are
    // what make the omission mean "unknown".
    mount({ age: 20, hypertension: true, heartDisease: true });
    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());

    group('high blood pressure').querySelectorAll('input[type=radio]')[2].click();
    save();

    await waitFor(() => expect(api.saveProfile).toHaveBeenCalled());
    const body = api.saveProfile.mock.calls[0][0];
    expect('hypertension' in body).toBe(false);
    expect(body.hypertension).toBeUndefined();
    // ...and the answer that WAS given still goes.
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
    // THE REPORTED DEFECT, and it was never a save bug -- the save was
    // verified working end to end. `analysisService.buildProfilePayload()`
    // reads the profile AT ANALYSIS TIME and stores the result on the report,
    // so a reader who answers these questions because the dashboard asked for
    // them sees the dashboard say exactly the same thing afterwards, and
    // concludes the form is broken. Same standing property as the explanation
    // cap and the clinician narrative.
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
    // It printed "Still blank: heartDisease" -- a key from the profile
    // document, at the person whose heart it is.
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

/**
 * THE TWO QUESTIONS AS DISCLOSURES.
 *
 * Asked for directly: closed after saving, opened again only when the reader
 * wants to change something, and never forced open on arrival. The safety
 * condition attached to that is the summary -- collapsing may not hide the
 * ANSWER, or a reader would have to open both boxes to find out what is
 * recorded, and "Not sure" would go out of sight on a form whose entire
 * purpose is that an unanswered question stays visible as unanswered.
 */
describe('the diagnosis questions collapse', () => {
  it('starts closed, on a profile with answers and on one without', async () => {
    mount({ age: 20, hypertension: true });
    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());
    expect(group('high blood pressure').open).toBe(false);
    expect(group('heart disease').open).toBe(false);
  });

  it('shows the recorded answer WITHOUT being opened', async () => {
    // The condition that makes closing safe.
    mount({ age: 20, hypertension: false, heartDisease: true });
    await waitFor(() => expect(group('high blood pressure')).toBeTruthy());

    expect(group('high blood pressure').open).toBe(false);
    expect(summaryAnswer('high blood pressure')).toBe('No');
    expect(summaryAnswer('heart disease')).toBe('Yes');
  });

  it('shows an UNANSWERED question as unanswered on the summary', async () => {
    // An absence must stay visible while the box is shut.
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
    // The obvious "help the reader" move, and it is wrong twice: it nags
    // someone who deliberately chose "prefer not to say" on every visit, and
    // it springs the boxes open again the instant a save completes -- which
    // is the behaviour being removed.
    mount({ age: 20, completeness: { fields: 7, filled: 5, percent: 71, missing: ['hypertension', 'heartDisease'] } });
    await waitFor(() => expect(group('heart disease')).toBeTruthy());

    expect(group('high blood pressure').open).toBe(false);
    expect(group('heart disease').open).toBe(false);
  });

  it('groups the radios for a screen reader without a second copy of the question', async () => {
    // `<fieldset>`/`<legend>` was replaced because a legend is painted over
    // its own top border. The grouping it provided is not optional, so it is
    // carried by role + label instead -- and the question is announced ONCE,
    // not by both a summary and a legend saying the same words.
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

/**
 * `answerLabel`'s FALLBACK, tested at the function.
 *
 * MUTATION-FOUND GAP. Changing the fallback from "Not sure" to "No" survived
 * every page-level test, because `null` matches the third option and the
 * fallback is only reached by a value that is none of true/false/null -- and
 * the form normalises to those three with `?? null`, so no rendering test can
 * produce the shape. Reaching it needs the exported function.
 *
 * It matters because the fallback is the only thing standing between an
 * unrecognised value and a summary that CLAIMS AN ANSWER. "No" against a
 * question nobody answered is an absence turned into a value, on the form
 * whose entire purpose is the opposite.
 */
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

