'use strict';

const ROLES = Object.freeze({
  PATIENT: 'patient',
  CLINICIAN: 'clinician',
  ADMIN: 'admin',
});

const ROLE_VALUES = Object.freeze(Object.values(ROLES));

module.exports = { ROLES, ROLE_VALUES };
