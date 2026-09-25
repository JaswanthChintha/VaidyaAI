/**
 * WHERE A VALUE CAME FROM -- and which sources are NOT measurements.
 *
 *   lab_report       measured by the laboratory
 *   patient_profile  typed into the reader's profile
 *   report_details   the sex / age PRINTED in the report's patient details,
 *                    used in place of the profile's (2026-09-25)
 *
 * Every screen that separates measured results from everything else used to
 * test `source === 'patient_profile'`. A third source would have fallen on
 * the MEASURED side of every one of those tests and shown "age 34" as a
 * laboratory result. This is the one test to use instead.
 */
export const NOT_MEASURED_SOURCES = new Set(['patient_profile', 'report_details']);

export function isPatientDetail(source) {
  return NOT_MEASURED_SOURCES.has(source);
}
