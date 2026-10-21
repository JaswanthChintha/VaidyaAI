export const NOT_MEASURED_SOURCES = new Set(['patient_profile', 'report_details']);

export function isPatientDetail(source) {
  return NOT_MEASURED_SOURCES.has(source);
}
