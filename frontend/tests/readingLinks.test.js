import { READING_LINKS } from '../src/lib/readingLinks';

/**
 * The further-reading links (2026-10-02). Fixed NHS pages only: a link that
 * carried a query string could carry something about the reader with it.
 */
const CATALOGUE_CODES = [
  'GENERAL_BALANCED_DIET',
  'GENERAL_DIETARY_FAT_QUALITY',
  'GENERAL_HYDRATION',
  'GENERAL_IRON_RICH_FOODS',
  'GENERAL_LIMIT_ADDED_SUGAR',
  'GENERAL_PHYSICAL_ACTIVITY',
  'GENERAL_SMOKING_CESSATION_SUPPORT',
  'GENERAL_VITAMIN_B12_SOURCES',
  'GENERAL_VITAMIN_D_SOURCES',
  'GENERAL_WEIGHT_DISCUSSION',
];

describe('further-reading links', () => {
  it('has one for every lifestyle topic the catalogue can produce', () => {
    for (const code of CATALOGUE_CODES) expect(READING_LINKS[code], code).toBeTruthy();
  });

  it('points only at fixed https pages on www.nhs.uk, with no query or fragment', () => {
    for (const [code, link] of Object.entries(READING_LINKS)) {
      const url = new URL(link.url);
      expect(url.protocol, code).toBe('https:');
      expect(url.hostname, code).toBe('www.nhs.uk');
      expect(url.search, code).toBe('');
      expect(url.hash, code).toBe('');
      expect(link.title.trim(), code).not.toBe('');
    }
  });
});
