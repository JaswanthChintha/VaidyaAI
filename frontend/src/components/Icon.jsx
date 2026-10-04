/**
 * A small set of line icons, drawn for this app at 24px on a 1.6 stroke.
 *
 * Decorative by default (`aria-hidden`): every icon sits beside words that
 * already say what it means, so a screen reader hears the words once rather
 * than an icon name and then the words.
 */
const PATHS = {
  reports: (
    <>
      <path d="M7 3.5h7.5L19 8v12.5H7z" />
      <path d="M14.5 3.5V8H19" />
      <path d="M10 12.5h6M10 16h6" />
    </>
  ),
  timeline: (
    <>
      <path d="M3.5 19.5h17" />
      <path d="M5 15.5l4.5-5 4 3L19 7" />
      <circle cx="19" cy="7" r="1.3" />
    </>
  ),
  profile: (
    <>
      <circle cx="12" cy="8.5" r="3.6" />
      <path d="M4.8 20c.9-3.6 3.8-5.6 7.2-5.6s6.3 2 7.2 5.6" />
    </>
  ),
  upload: (
    <>
      <path d="M12 15.5V4.5" />
      <path d="M7.5 9 12 4.5 16.5 9" />
      <path d="M4.5 15v4.5h15V15" />
    </>
  ),
  read: (
    <>
      <path d="M4 5.5h16v13H4z" />
      <path d="M7.5 9.5h4M7.5 12.5h9M7.5 15.5h6" />
    </>
  ),
  check: (
    <>
      <path d="M12 3.5 19 6v5.5c0 4.4-3 7.7-7 9-4-1.3-7-4.6-7-9V6z" />
      <path d="m8.8 12 2.2 2.2 4.2-4.4" />
    </>
  ),
  explain: (
    <>
      <path d="M4.5 5.5h15v10h-8L7 19.5v-4H4.5z" />
      <path d="M8.5 9.5h7M8.5 12h4.5" />
    </>
  ),
  doctor: (
    <>
      <path d="M7 4v5a4 4 0 0 0 8 0V4" />
      <path d="M11 13v2.5a4.5 4.5 0 0 0 9 0V13" />
      <circle cx="20" cy="11" r="1.8" />
    </>
  ),
  people: (
    <>
      <circle cx="9" cy="8.5" r="3" />
      <path d="M3.5 19c.7-3 2.9-4.7 5.5-4.7s4.8 1.7 5.5 4.7" />
      <circle cx="16.5" cy="9.5" r="2.4" />
      <path d="M16 14.4c2.3.1 4 1.6 4.5 4.1" />
    </>
  ),
  signout: (
    <>
      <path d="M14 4.5H5.5v15H14" />
      <path d="M10 12h10M16.5 8.5 20 12l-3.5 3.5" />
    </>
  ),
  arrow: <path d="M5 12h14M13.5 6.5 19 12l-5.5 5.5" />,
  leaf: (
    <>
      <path d="M5 19c0-8 5-13.5 14-14-.5 9-6 14-14 14z" />
      <path d="M5 19 13 11" />
    </>
  ),
};

export default function Icon({ name, size = 20, className }) {
  return (
    <svg
      className={className ? `icon ${className}` : 'icon'}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
