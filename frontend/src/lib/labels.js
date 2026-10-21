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

  alt: 'ALT (SGPT)',
  ast: 'AST (SGOT)',
  bilirubin_total: 'Total bilirubin',
};

export const PROFILE_FIELD_LABEL = {
  age: 'age',
  gender: 'sex',
  heightCm: 'height',
  weightKg: 'weight',
  smokingHistory: 'smoking history',
  hypertension: 'diagnosed high blood pressure',
  heartDisease: 'diagnosed heart disease',
};

export function profileFieldLabel(field) {
  return PROFILE_FIELD_LABEL[field] || field;
}
