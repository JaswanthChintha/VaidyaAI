/**
 * Further reading for each lifestyle topic (Module 26's catalogue codes).
 *
 * ONE FIXED PAGE PER CODE, on the NHS website -- free, ad-free and written
 * for patients. Every URL was opened and its page title checked against the
 * topic on 2026-10-02.
 *
 * NOTHING ABOUT THE READER LEAVES THIS APP. The links carry no query string
 * and are opened with `rel="noopener noreferrer"`, so the NHS site is not
 * even told which page the reader came from. A code with no entry here simply
 * gets no link -- never a search URL built from a condition name.
 */
export const READING_SOURCE = 'NHS website';

export const READING_LINKS = {
  GENERAL_BALANCED_DIET: {
    title: 'Eat well',
    url: 'https://www.nhs.uk/live-well/eat-well/',
  },
  GENERAL_DIETARY_FAT_QUALITY: {
    title: 'Facts about fat',
    url: 'https://www.nhs.uk/live-well/eat-well/food-types/different-fats-nutrition/',
  },
  GENERAL_HYDRATION: {
    title: 'Water, drinks and hydration',
    url: 'https://www.nhs.uk/live-well/eat-well/food-guidelines-and-food-labels/water-drinks-nutrition/',
  },
  GENERAL_IRON_RICH_FOODS: {
    title: 'Iron',
    url: 'https://www.nhs.uk/conditions/vitamins-and-minerals/iron/',
  },
  GENERAL_LIMIT_ADDED_SUGAR: {
    title: 'Sugar: the facts',
    url: 'https://www.nhs.uk/live-well/eat-well/food-types/how-does-sugar-in-our-diet-affect-our-health/',
  },
  GENERAL_PHYSICAL_ACTIVITY: {
    title: 'Physical activity guidelines for adults',
    url: 'https://www.nhs.uk/live-well/exercise/physical-activity-guidelines-for-adults-aged-19-to-64/',
  },
  GENERAL_SMOKING_CESSATION_SUPPORT: {
    title: 'Quit smoking',
    url: 'https://www.nhs.uk/live-well/quit-smoking/',
  },
  GENERAL_VITAMIN_B12_SOURCES: {
    title: 'B vitamins and folic acid',
    url: 'https://www.nhs.uk/conditions/vitamins-and-minerals/vitamin-b/',
  },
  GENERAL_VITAMIN_D_SOURCES: {
    title: 'Vitamin D',
    url: 'https://www.nhs.uk/conditions/vitamins-and-minerals/vitamin-d/',
  },
  GENERAL_WEIGHT_DISCUSSION: {
    title: 'Healthy weight',
    url: 'https://www.nhs.uk/live-well/healthy-weight/',
  },
};
