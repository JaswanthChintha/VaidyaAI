'use strict';

const mongoose = require('mongoose');
const {
  isOwner,
  canAccess,
  assertCanAccess,
  ownerScopedFilter,
  requireOwnership,
} = require('../src/utils/ownership');
const ApiError = require('../src/utils/ApiError');
const { ROLES } = require('../src/utils/roles');

const idA = new mongoose.Types.ObjectId();
const idB = new mongoose.Types.ObjectId();

const patient = { id: idA.toString(), role: ROLES.PATIENT };
const otherPatient = { id: idB.toString(), role: ROLES.PATIENT };
const admin = { id: new mongoose.Types.ObjectId().toString(), role: ROLES.ADMIN };
const clinician = { id: new mongoose.Types.ObjectId().toString(), role: ROLES.CLINICIAN };

// Generic record shape - Module 1 owns no record collection, so this stands in
// for anything a later module associates with a user.
const record = { _id: new mongoose.Types.ObjectId(), user: idA };

describe('ownership.isOwner', () => {
  it('is true when the owner field matches the user id', () => {
    expect(isOwner(patient, record)).toBe(true);
  });

  it('is false for a different user', () => {
    expect(isOwner(otherPatient, record)).toBe(false);
  });

  it('compares ObjectId, string and populated-document owners equivalently', () => {
    expect(isOwner(patient, { user: idA })).toBe(true);
    expect(isOwner(patient, { user: idA.toString() })).toBe(true);
    expect(isOwner(patient, { user: { _id: idA, name: 'Asha' } })).toBe(true);
    expect(isOwner({ _id: idA }, { user: idA })).toBe(true);
  });

  it('supports a custom and a nested owner field', () => {
    expect(isOwner(patient, { owner: idA }, { ownerField: 'owner' })).toBe(true);
    expect(isOwner(patient, { meta: { createdBy: idA } }, { ownerField: 'meta.createdBy' })).toBe(
      true
    );
  });

  it('is false for missing user, missing resource or missing owner field', () => {
    expect(isOwner(null, record)).toBe(false);
    expect(isOwner(patient, null)).toBe(false);
    expect(isOwner(patient, {})).toBe(false);
    expect(isOwner({ role: ROLES.PATIENT }, record)).toBe(false);
  });

  it('ignores role - admins are not "owners"', () => {
    expect(isOwner(admin, record)).toBe(false);
  });
});

describe('ownership.canAccess', () => {
  it('allows the owner', () => {
    expect(canAccess(patient, record)).toBe(true);
  });

  it('denies an unrelated patient', () => {
    expect(canAccess(otherPatient, record)).toBe(false);
  });

  // INVERTED (was: "allows an admin by default"). `allowRoles` now defaults to
  // `[]` - deny by default. An opt-OUT bypass fails open: any future module
  // touching patient data would inherit it by forgetting to opt out. Section 19
  // grants no staff exception to "users can access only their own medical
  // information". The capability still exists; it must now be asked for.
  it('denies an admin by default (no implicit privileged bypass)', () => {
    expect(canAccess(admin, record)).toBe(false);
  });

  it('denies a clinician by default', () => {
    expect(canAccess(clinician, record)).toBe(false);
  });

  it('honours a custom allowRoles list', () => {
    expect(canAccess(clinician, record, { allowRoles: [ROLES.CLINICIAN] })).toBe(true);
    expect(canAccess(admin, record, { allowRoles: [] })).toBe(false);
  });

  // The bypass capability must remain available for resources where staff
  // access is genuinely warranted (audit logs, user administration) - it just
  // has to be granted explicitly and deliberately at the call site.
  it('allows an admin when the bypass is granted explicitly', () => {
    expect(canAccess(admin, record, { allowRoles: [ROLES.ADMIN] })).toBe(true);
  });
});

describe('ownership.assertCanAccess', () => {
  it('passes for the owner', () => {
    expect(assertCanAccess(patient, record)).toBe(true);
  });

  it('throws 404 when the resource is missing (no existence leak)', () => {
    expect(() => assertCanAccess(patient, null)).toThrow(ApiError);
    try {
      assertCanAccess(patient, null);
    } catch (err) {
      expect(err.statusCode).toBe(404);
      expect(err.code).toBe('NOT_FOUND');
    }
  });

  it('throws 403 for somebody else\'s record', () => {
    try {
      assertCanAccess(otherPatient, record);
      throw new Error('should have thrown');
    } catch (err) {
      expect(err.statusCode).toBe(403);
      expect(err.code).toBe('OWNERSHIP_REQUIRED');
    }
  });
});

describe('ownership.ownerScopedFilter', () => {
  it('scopes a query to the requesting user', () => {
    expect(ownerScopedFilter(patient)).toEqual({ user: patient.id });
  });

  it('merges a base filter', () => {
    expect(ownerScopedFilter(patient, { base: { status: 'ready' } })).toEqual({
      status: 'ready',
      user: patient.id,
    });
  });

  // INVERTED (was: "leaves the filter unscoped for privileged roles"). Deny by
  // default: an admin's query is scoped to their own documents like anyone
  // else's unless the bypass is granted explicitly.
  it('scopes an admin to their own documents by default', () => {
    expect(ownerScopedFilter(admin, { base: { status: 'ready' } })).toEqual({
      status: 'ready',
      user: admin.id,
    });
  });

  it('leaves the filter unscoped when the bypass is granted explicitly', () => {
    expect(
      ownerScopedFilter(admin, { base: { status: 'ready' }, allowRoles: [ROLES.ADMIN] })
    ).toEqual({ status: 'ready' });
  });

  it('uses a custom owner field', () => {
    expect(ownerScopedFilter(patient, { ownerField: 'patientId' })).toEqual({
      patientId: patient.id,
    });
  });
});

describe('ownership.requireOwnership middleware', () => {
  const runMiddleware = (middleware, req) =>
    new Promise((resolve) => middleware(req, {}, (err) => resolve(err)));

  it('calls next() and attaches the resource for the owner', async () => {
    const middleware = requireOwnership(async () => record);
    const req = { user: patient };
    const err = await runMiddleware(middleware, req);

    expect(err).toBeUndefined();
    expect(req.resource).toBe(record);
  });

  it('passes a 403 to next() for a non-owner', async () => {
    const middleware = requireOwnership(async () => record);
    const err = await runMiddleware(middleware, { user: otherPatient });

    expect(err).toBeInstanceOf(ApiError);
    expect(err.statusCode).toBe(403);
  });

  it('passes a 404 to next() when the loader finds nothing', async () => {
    const middleware = requireOwnership(async () => null);
    const err = await runMiddleware(middleware, { user: patient });

    expect(err.statusCode).toBe(404);
  });

  it('passes a 401 to next() when the request is unauthenticated', async () => {
    const middleware = requireOwnership(async () => record);
    const err = await runMiddleware(middleware, {});

    expect(err.statusCode).toBe(401);
  });

  it('propagates loader failures to next()', async () => {
    const boom = new Error('db exploded');
    const middleware = requireOwnership(async () => {
      throw boom;
    });
    const err = await runMiddleware(middleware, { user: patient });

    expect(err).toBe(boom);
  });

  it('supports a custom attachAs key', async () => {
    const middleware = requireOwnership(async () => record, { attachAs: 'report' });
    const req = { user: patient };
    await runMiddleware(middleware, req);

    expect(req.report).toBe(record);
  });
});
