/**
 * What a patient is called each parameter, in the register a reader uses.
 *
 * SHARED BECAUSE A SECOND COPY DRIFTS. The dashboard and the timeline's trend
 * charts both name the same eleven features, and two tables of the same names
 * is how one of them ends up saying `blood_glucose` to a patient.
 *
 * These are TABLE-ROW HEADINGS and a chart's subject line. They are not
 * always right mid-sentence -- "this model had no value for Smoking history
 * (reported)" is not English -- so a caller writing prose needs its own
 * wording, not this table (MEMORY.md 6w, `readableFeature`).
 */
export const PATIENT_LABEL = {
  hba1c: 'HbA1c (average blood sugar)',
  blood_glucose: 'Blood sugar',
  cholesterol: 'Total cholesterol',
  triglycerides: 'Triglycerides',
  creatinine: 'Creatinine (kidney marker)',
  hemoglobin: 'Haemoglobin',
  vitamin_d: 'Vitamin D',
  vitamin_b12: 'Vitamin B12',
  bmi: 'BMI',
  age: 'age',
  gender: 'sex',
  smoking_history: 'smoking history',
  hypertension: 'history of high blood pressure',
  heart_disease: 'history of heart disease',

  // ---- the complete blood count ----
  //
  // ⚠ ADDED AFTER THEY REACHED A READER AS RAW KEYS. A feature with no row
  // here falls back to the producer's `subject`, which is built as
  // `f"the {feature} result"` from the CANONICAL NAME -- so the explanation
  // headings on a real dashboard read:
  //
  //     "the rbc_count result"   "the wbc_count result"   "the mcv result"
  //
  // Underscores and internal identifiers, in the register a patient reads.
  // The same class of defect as the profile page's "Still blank:
  // heartDisease" recorded below.
  //
  // WORDS A READER USES, not the analyser's. "Red blood cell count", not
  // "erythrocyte count"; "Haematocrit (PCV)" carries the abbreviation the
  // report itself prints, because a reader matching this screen against the
  // paper needs to find the row.
  //
  // ⚠ NO PARENTHESISED ABBREVIATION HERE. This string is the table's SUB-LINE
  // and the laboratory's printed name is the heading directly above it, so
  // "Average red cell size (MCV)" under a heading of "MCV" says it twice.
  hematocrit: 'Haematocrit',
  rbc_count: 'Red blood cell count',
  mcv: 'Average red cell size',
  mch: 'Average haemoglobin per red cell',
  mchc: 'Haemoglobin concentration in red cells',
  wbc_count: 'White blood cell count',
  neutrophils: 'Neutrophils',
  lymphocytes: 'Lymphocytes',
  monocytes: 'Monocytes',
  eosinophils: 'Eosinophils',
  basophils: 'Basophils',
  platelet_count: 'Platelet count',

  // ---- the liver panel (2026-10-04) ----
  // The names Indian reports print beside the formal ones, so a reader can
  // find the row on the paper.
  alt: 'ALT (SGPT)',
  ast: 'AST (SGOT)',
  bilirubin_total: 'Total bilirubin',
};

/**
 * The profile form's own field names, as a reader knows them.
 *
 * SEPARATE FROM `PATIENT_LABEL` ON PURPOSE. That table is keyed by Module 5's
 * snake_case feature names (`heart_disease`); these are the Module 2 profile
 * document's camelCase keys (`heartDisease`), and the completeness payload
 * speaks the second vocabulary. Merging them would mean one table answering
 * to two key styles, which is how a lookup silently misses and prints the raw
 * key -- which is exactly the defect this fixes: the profile page told the
 * reader "Still blank: heartDisease".
 *
 * These read as a LIST ITEM ("Still blank: ...") and match the question the
 * form asks above, so a reader can find the thing they are told is missing.
 */
export const PROFILE_FIELD_LABEL = {
  age: 'age',
  gender: 'sex',
  heightCm: 'height',
  weightKg: 'weight',
  smokingHistory: 'smoking history',
  hypertension: 'diagnosed high blood pressure',
  heartDisease: 'diagnosed heart disease',
};

/** A profile field name in words, falling back to the key it could not map. */
export function profileFieldLabel(field) {
  return PROFILE_FIELD_LABEL[field] || field;
}
