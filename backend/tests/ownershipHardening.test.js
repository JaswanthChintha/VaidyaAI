'use strict';

const mongoose = require('mongoose');
const {
  OWNER_ONLY,
  canAccess,
  assertCanAccess,
  ownerScopedFilter,
} = require('../src/utils/ownership');
const { ROLES } = require('../src/utils/roles');

/**
 * Regression tests for the two footguns Module 1's audit flagged in
 * ownership.js, fixed before Module 2 became its first real consumer.
 */

const idA = new mongoose.Types.ObjectId();
const patient = { id: idA.toString(), role: ROLES.PATIENT };
const admin = { id: new mongoose.Types.ObjectId().toString(), role: ROLES.ADMIN };
const record = { _id: new mongoose.Types.ObjectId(), user: idA };

describe('ownerScopedFilter refuses to build an unscoped filter', () => {
  // Previously these returned `{ user: null }` - a valid Mongo filter matching
  // every document with a null/absent owner, i.e. silent data exposure.
  it('throws for a null user', () => {
    expect(() => ownerScopedFilter(null)).toThrow(/authenticated user/i);
  });

  it('throws for undefined', () => {
    expect(() => ownerScopedFilter(undefined)).toThrow(/authenticated user/i);
  });

  it('throws for a user object with no id', () => {
    expect(() => ownerScopedFilter({ role: ROLES.PATIENT })).toThrow(/authenticated user/i);
  });

  it('never returns a filter whose owner value is null or undefined', () => {
    const filter = ownerScopedFilter(patient);
    expect(filter.user).toBe(patient.id);
    expect(filter.user).not.toBeNull();
  });

  it('still throws for an identity-less caller even under OWNER_ONLY', () => {
    expect(() => ownerScopedFilter(null, { ...OWNER_ONLY })).toThrow();
  });
});

describe('ownership denies by default, and OWNER_ONLY restates it', () => {
  // The default is now `allowRoles: []`. OWNER_ONLY is consequently identical
  // to it - kept as belt-and-braces so health-data call sites stay denying even
  // if the default is ever loosened again.
  it('the generic default denies a non-owner admin', () => {
    expect(canAccess(admin, record)).toBe(false);
    expect(ownerScopedFilter(admin)).toEqual({ user: admin.id });
  });

  it('an explicit grant still restores the bypass where warranted', () => {
    expect(canAccess(admin, record, { allowRoles: [ROLES.ADMIN] })).toBe(true);
    expect(ownerScopedFilter(admin, { allowRoles: [ROLES.ADMIN] })).toEqual({});
  });

  it('OWNER_ONLY denies an admin who is not the owner', () => {
    expect(canAccess(admin, record, { ...OWNER_ONLY })).toBe(false);
  });

  it('OWNER_ONLY scopes an admin query to their own documents', () => {
    expect(ownerScopedFilter(admin, { ...OWNER_ONLY })).toEqual({ user: admin.id });
  });

  it('OWNER_ONLY still allows the genuine owner', () => {
    expect(canAccess(patient, record, { ...OWNER_ONLY })).toBe(true);
    expect(assertCanAccess(patient, record, { ...OWNER_ONLY })).toBe(true);
  });

  it('preserves 404-before-403 under OWNER_ONLY', () => {
    expect(() => assertCanAccess(admin, null, { ...OWNER_ONLY })).toThrow(
      expect.objectContaining({ statusCode: 404 })
    );
    expect(() => assertCanAccess(admin, record, { ...OWNER_ONLY })).toThrow(
      expect.objectContaining({ statusCode: 403, code: 'OWNERSHIP_REQUIRED' })
    );
  });

  it('OWNER_ONLY is frozen so a caller cannot mutate the shared preset', () => {
    expect(Object.isFrozen(OWNER_ONLY)).toBe(true);
    expect(Object.isFrozen(OWNER_ONLY.allowRoles)).toBe(true);
  });
});
