import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import Logo, { LOGO_DROP, LOGO_PULSE } from '../src/components/Logo';
import Landing from '../src/pages/Landing';
import { AuthProvider } from '../src/lib/auth';

/**
 * The drop + pulse logo (owner's choice, 2026-10-06) is drawn in three places
 * -- Logo.jsx, the splash, and public/favicon.svg -- from the same two paths.
 * These tests keep the three from drifting apart.
 */
describe('the logo', () => {
  it('draws a tile, the drop and the pulse, hidden from screen readers', () => {
    const { container } = render(<Logo size={40} />);
    const svg = container.querySelector('svg.logo');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('width', '40');
    expect(container.querySelector('.logo__drop')).toHaveAttribute('d', LOGO_DROP);
    expect(container.querySelector('.logo__pulse')).toHaveAttribute('d', LOGO_PULSE);
  });

  it('the browser-tab icon uses the same drop and pulse', () => {
    const favicon = readFileSync(resolve(__dirname, '../public/favicon.svg'), 'utf8');
    expect(favicon).toContain(`d="${LOGO_DROP}"`);
    expect(favicon).toContain(`d="${LOGO_PULSE}"`);
    const html = readFileSync(resolve(__dirname, '../index.html'), 'utf8');
    expect(html).toContain('<link rel="icon" type="image/svg+xml" href="/favicon.svg" />');
  });

  it('is the mark in the landing header, and the old leaf mark is gone', () => {
    const { container } = render(
      <MemoryRouter>
        <AuthProvider>
          <Landing />
        </AuthProvider>
      </MemoryRouter>
    );
    const brand = container.querySelector('.landing__brand');
    expect(brand.querySelector('svg.logo .logo__pulse')).not.toBeNull();
    expect(brand.querySelector('span.nav__mark')).toBeNull();
  });

  it('the example table rows carry their animation order', () => {
    const { container } = render(
      <MemoryRouter>
        <AuthProvider>
          <Landing />
        </AuthProvider>
      </MemoryRouter>
    );
    const rows = [...container.querySelectorAll('.specimen__table tbody tr')];
    expect(rows.map((r) => r.style.getPropertyValue('--i'))).toEqual(['0', '1', '2']);
  });
});
