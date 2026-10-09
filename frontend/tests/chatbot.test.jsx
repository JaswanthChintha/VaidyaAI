import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChatBot, { GENERAL_SUGGESTIONS, REPORT_SUGGESTIONS } from '../src/components/ChatBot';
import App from '../src/App';
import { AuthProvider } from '../src/lib/auth';
import { api, ApiError } from '../src/lib/api';

/**
 * The chatbot panel (2026-10-09). A bubble on signed-in pages; general
 * questions anywhere, questions about THE report on a report's own pages.
 */

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
    vi.spyOn(api, 'chat').mockRejectedValue(new ApiError(502, 'AI_SERVICE_ERROR', 'boom'));
    mountAt('/reports');
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    fireEvent.click(screen.getByRole('button', { name: 'What is HbA1c?' }));
    expect(await screen.findByText(/isn't available right now/)).toBeInTheDocument();
    expect(screen.queryByText('boom')).not.toBeInTheDocument();
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
