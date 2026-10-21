import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChatBot, { GENERAL_SUGGESTIONS, REPORT_SUGGESTIONS, SLOW_AFTER_MS } from '../src/components/ChatBot';
import App from '../src/App';
import { AuthProvider } from '../src/lib/auth';
import { api, ApiError } from '../src/lib/api';


const REPORT_ID = 'abcdefabcdefabcdefabcdef';

function mountAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<ChatBot />} />
      </Routes>
    </MemoryRouter>
  );
}

const ANSWER = {
  chat: {
    outcome: 'answered',
    answer: 'Open the Reports page and press Upload.',
    sources: [{ kind: 'app_help', title: 'Uploading a report' }],
  },
  usedReport: false,
};

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('the chat bubble and panel', () => {
  it('starts as a bubble and opens to general suggestions', () => {
    mountAt('/reports');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    expect(screen.getByRole('dialog', { name: 'Ask VaidyaAI' })).toBeInTheDocument();
    for (const s of GENERAL_SUGGESTIONS) expect(screen.getByRole('button', { name: s })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: REPORT_SUGGESTIONS[0] })).not.toBeInTheDocument();
  });

  it('a general question is sent without a report id, and the answer shows its source', async () => {
    const chat = vi.spyOn(api, 'chat').mockResolvedValue(ANSWER);
    mountAt('/timeline');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    fireEvent.click(screen.getByRole('button', { name: 'How do I upload a report?' }));

    expect(await screen.findByText('Open the Reports page and press Upload.')).toBeInTheDocument();
    expect(chat).toHaveBeenCalledWith('How do I upload a report?', null);
    expect(screen.getByText(/From: VaidyaAI help – Uploading a report/)).toBeInTheDocument();
  });

  it("on a report's page it offers report questions and sends that report's id", async () => {
    const chat = vi.spyOn(api, 'chat').mockResolvedValue(ANSWER);
    mountAt(`/reports/${REPORT_ID}/doctor-summary`);
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    fireEvent.click(screen.getByRole('button', { name: REPORT_SUGGESTIONS[0] }));
    await waitFor(() => expect(chat).toHaveBeenCalledWith(REPORT_SUGGESTIONS[0], REPORT_ID));
    expect(screen.getByText(/this report's results are sent to an outside AI service/)).toBeInTheDocument();
  });

  it('typed questions are trimmed, sent once, and the box empties', async () => {
    const chat = vi.spyOn(api, 'chat').mockResolvedValue(ANSWER);
    mountAt('/reports');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    const input = screen.getByLabelText('Your question');
    fireEvent.change(input, { target: { value: '  What is HbA1c?  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Open the Reports page and press Upload.');
    expect(chat).toHaveBeenCalledTimes(1);
    expect(chat).toHaveBeenCalledWith('What is HbA1c?', null);
    expect(input.value).toBe('');
  });

  it('Send is disabled for an empty box', () => {
    mountAt('/reports');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('too many questions -> a plain "please wait", not an error dump', async () => {
    vi.spyOn(api, 'chat').mockRejectedValue(new ApiError(429, 'RATE_LIMIT_EXCEEDED', 'Too many requests'));
    mountAt('/reports');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    fireEvent.click(screen.getByRole('button', { name: 'What is HbA1c?' }));
    expect(await screen.findByText(/asked a lot of questions/)).toBeInTheDocument();
  });

  it('any other failure -> "not available right now"', async () => {
    vi.spyOn(api, 'chat').mockRejectedValue(new ApiError(500, 'INTERNAL_ERROR', 'boom'));
    mountAt('/reports');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    fireEvent.click(screen.getByRole('button', { name: 'What is HbA1c?' }));
    expect(await screen.findByText(/isn't available right now/)).toBeInTheDocument();
    expect(screen.queryByText('boom')).not.toBeInTheDocument();
  });

  it('the assistant still waking at the deadline -> "waking up, try again in a minute"', async () => {
    vi.spyOn(api, 'chat').mockRejectedValue(
      new ApiError(503, 'ASSISTANT_WAKING', 'The assistant is waking up. Please try again in a minute.')
    );
    mountAt('/reports');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    fireEvent.click(screen.getByRole('button', { name: 'What is HbA1c?' }));
    expect(await screen.findByText('The assistant is waking up. Please try again in a minute.')).toBeInTheDocument();
  });

  it.each(['AI_SERVICE_ERROR', 'AI_SERVICE_BUSY', 'AI_SERVICE_TIMEOUT', 'AI_SERVICE_UNAVAILABLE'])(
    '%s -> "could not answer just now", never the server\'s own words',
    async (code) => {
      vi.spyOn(api, 'chat').mockRejectedValue(new ApiError(502, code, 'The analysis service failed'));
      mountAt('/reports');
      fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
      fireEvent.click(screen.getByRole('button', { name: 'What is HbA1c?' }));
      expect(
        await screen.findByText('The assistant could not answer just now. Please try again in a minute.')
      ).toBeInTheDocument();
      expect(screen.queryByText(/analysis service/)).not.toBeInTheDocument();
    }
  );

  it('a long wait says the assistant may be waking up; the answer replaces it', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let answer;
      vi.spyOn(api, 'chat').mockImplementation(() => new Promise((resolve) => { answer = resolve; }));
      mountAt('/reports');
      fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
      fireEvent.click(screen.getByRole('button', { name: 'What is HbA1c?' }));

      expect(screen.getByRole('status')).toHaveTextContent('Thinking…');
      await act(async () => {
        vi.advanceTimersByTime(SLOW_AFTER_MS - 100);
      });
      expect(screen.getByRole('status')).toHaveTextContent('Thinking…');
      await act(async () => {
        vi.advanceTimersByTime(200);
      });
      expect(screen.getByRole('status')).toHaveTextContent(
        'Still working… the assistant may be waking up, which can take up to two minutes.'
      );

      await act(async () => {
        answer(ANSWER);
      });
      expect(await screen.findByText('Open the Reports page and press Upload.')).toBeInTheDocument();
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('closes with the close button and with Escape', () => {
    mountAt('/reports');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close chat' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('only for signed-in users', () => {
  it('the landing page (signed out) has no chat bubble', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    );
    expect(screen.queryByRole('button', { name: 'Open chat' })).not.toBeInTheDocument();
  });
});
