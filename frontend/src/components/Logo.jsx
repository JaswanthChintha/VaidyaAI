/**
 * The VaidyaAI mark (owner's choice, 2026-10-06): a blood drop with a pulse
 * line across it -- a lab sample, read -- on a rounded forest tile.
 *
 * Colours come from theme tokens (styles.css: --brand, --logo-drop), so the
 * mark follows light and dark mode with no second drawing. The same paths are
 * drawn in `public/favicon.svg` and animated by `Splash.jsx`; change them in
 * all three together.
 */
export const LOGO_DROP = 'M24 9c6 8 11 13.5 11 20a11 11 0 0 1-22 0c0-6.5 5-12 11-20z';
export const LOGO_PULSE = 'M14 30h5l2.5-5 4 9 2.5-4H34';

export default function Logo({ size = 32, className }) {
  return (
    <svg
      className={className ? `logo ${className}` : 'logo'}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      aria-hidden="true"
      focusable="false"
    >
      <rect className="logo__tile" width="48" height="48" rx="13" />
      <path className="logo__drop" d={LOGO_DROP} />
      <path className="logo__pulse" d={LOGO_PULSE} />
    </svg>
  );
}
