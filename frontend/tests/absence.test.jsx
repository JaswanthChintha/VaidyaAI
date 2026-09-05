import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Absent, Risk, Section, Value } from '../src/components/Absent';
import { formatValue, isPresent } from '../src/lib/absence';

/**
 * The frontend half of "absence is never a value".
 *
 * Every layer beneath this one was made careful about absence at real cost --
 * and all of it can be undone by one line of JSX. These tests hold the
 * rendering side of the guarantee, in the exact shapes the audits behind
 * MEMORY.md section 11 found being got wrong elsewhere.
 */

describe('isPresent', () => {
  it('treats 0 and false as VALUES, not absences', () => {
    // This is the whole reason `||` may not appear next to a clinical value.
    // A vitamin D of 0 is a reading; `value || 'Not measured'` erases it.
    expect(isPresent(0)).toBe(true);
    expect(isPresent(false)).toBe(true);
    expect(isPresent('')).toBe(true);
  });

  it('treats null, undefined and NaN as absences', () => {
    expect(isPresent(null)).toBe(false);
    expect(isPresent(undefined)).toBe(false);
    expect(isPresent(NaN)).toBe(false);
  });
});

describe('formatValue', () => {
  it('returns null rather than the strings "null" or "undefined"', () => {
    // Both have reached real screens on other projects and read, to a
    // patient, as a result.
    expect(formatValue(null, '%')).toBeNull();
    expect(formatValue(undefined)).toBeNull();
  });

  it('prints a real zero', () => {
    expect(formatValue(0, 'ng/ml')).toBe('0 ng/ml');
  });

  it('does not invent precision', () => {
    expect(formatValue(5.5, '%')).toBe('5.5 %');
    expect(formatValue(0.9999808, 'mg/dl')).toBe('1 mg/dl');
  });
});

describe('Value', () => {
  it('renders a measured value', () => {
    render(<Value value={6.8} unit="%" />);
    expect(screen.getByText('6.8 %')).toBeInTheDocument();
  });

  it('renders a real zero rather than treating it as missing', () => {
    render(<Value value={0} unit="ng/ml" />);
    expect(screen.getByText('0 ng/ml')).toBeInTheDocument();
  });

  it('branches on `available`, not on the value', () => {
    // Module 31 sends `available: false` with no comparison object at all;
    // Module 23 sends `generated_explanation_available` beside a possibly
    // empty string. The FLAG decides, always.
    render(
      <Value
        value={42}
        available={false}
        reason="No population group matched your age and sex."
      />
    );
    expect(screen.queryByText('42')).not.toBeInTheDocument();
    expect(
      screen.getByText('No population group matched your age and sex.')
    ).toBeInTheDocument();
  });

  it('shows an absence when there is nothing to show', () => {
    render(<Value value={null} reason="This reading was not on the report." />);
    expect(screen.getByText('Not measured')).toBeInTheDocument();
  });

  it('takes no fallback VALUE prop at all', () => {
    // The whole class of bug is someone reaching for `defaultValue` under
    // deadline. There is deliberately nowhere to put one.
    render(<Value value={null} defaultValue={0} reason="unmeasured" />);
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    expect(screen.getByText('Not measured')).toBeInTheDocument();
  });
});

describe('Risk', () => {
  it('renders a real risk level', () => {
    render(<Risk risk="High" />);
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('NEVER renders a missing risk as Low', () => {
    // The exact defect an audit found in the backend: an explicit `risk: null`
    // was overridden with "Low", so a card printed "Not Assessed" beside a
    // reassuring risk level. `INSUFFICIENT_DATA` carries no risk.
    render(<Risk risk={null} />);
    expect(screen.queryByText('Low')).not.toBeInTheDocument();
    expect(screen.getByText('Not measured')).toBeInTheDocument();
  });

  it('refuses a risk when nothing was assessed, even if one is supplied', () => {
    render(<Risk risk="Low" assessed={false} />);
    expect(screen.queryByText('Low')).not.toBeInTheDocument();
  });
});

describe('Section', () => {
  it('renders children when the section is present', () => {
    render(
      <Section status={{ present: true }} title="Trends">
        <p>a trend</p>
      </Section>
    );
    expect(screen.getByText('a trend')).toBeInTheDocument();
  });

  it('states the reason instead of implying stability', () => {
    // With one report a trend section is absent because a trend needs two
    // readings. Rendering that as "stable" states something nobody measured
    // -- Module 28 reserves that word for a change measured against a
    // declared stability band.
    render(
      <Section
        status={{
          present: false,
          reason_code: 'SINGLE_REPORT_ONLY',
          reason:
            'Only one report was supplied. This is not a finding of stability.',
        }}
        title="Trends"
      >
        <p>a trend</p>
      </Section>
    );
    expect(screen.queryByText('a trend')).not.toBeInTheDocument();
    expect(screen.getByText(/not a finding of stability/)).toBeInTheDocument();
    expect(screen.getByText('SINGLE_REPORT_ONLY')).toBeInTheDocument();
  });

  it('never renders a section as absent without saying why', () => {
    render(<Section status={{ present: false }} title="Trends" />);
    expect(screen.getByText('This section is not available.')).toBeInTheDocument();
  });
});

describe('Absent', () => {
  it('carries the reason so "we did not look" is distinguishable from "nothing found"', () => {
    render(<Absent reason="The laboratory did not report this value." />);
    expect(
      screen.getByText('The laboratory did not report this value.')
    ).toBeInTheDocument();
  });
});
