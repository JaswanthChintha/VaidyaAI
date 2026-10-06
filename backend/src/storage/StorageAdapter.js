'use strict';

/**
 * Module 3 - storage adapter interface.
 *
 * Report FILES live behind this interface; report METADATA lives in MongoDB
 * (src/models/Report.js). The only thing the database stores about a file's
 * location is an opaque `storageKey` string plus the `storageDriver` that
 * produced it, so swapping local disk for a cloud bucket later is adding one
 * file in this directory and changing STORAGE_DRIVER - no controller, model or
 * route changes.
 *
 * A key is opaque to every caller. The local adapter happens to use
 * `<userId>/<random>.<ext>`, but nothing outside the adapter may parse, join or
 * otherwise interpret it.
 *
 * Contract every adapter must satisfy:
 *
 *   get name(): string
 *     Stable identifier persisted on each report (`local`, `s3`, ...).
 *
 *   async save({ userId, buffer, extension }): Promise<{ key, size }>
 *     Writes the bytes and returns the key needed to read them back. The
 *     adapter - not the caller - chooses the key; it must never be derived from
 *     client input. Throws on failure, having left nothing behind.
 *
 *   async createReadStream(key): Promise<Readable>
 *     Streams the stored object. Throws a 404 ApiError when the key resolves to
 *     nothing, and refuses any key that escapes the adapter's own namespace.
 *
 *   async stat(key): Promise<{ size: number }|null>
 *     Size of the stored object, or null when it is absent.
 *
 *   async remove(key): Promise<boolean>
 *     Deletes the object. Resolves `false` when it was already gone (delete is
 *     idempotent - a missing file must never fail a report deletion, or an
 *     orphaned DB row becomes undeletable).
 *
 *   async removeUserScope(userId): Promise<void>
 *     Best-effort removal of a user's whole namespace. Used by tests and by any
 *     future account-deletion flow.
 *
 * Adapters must never log file contents.
 */

class StorageAdapter {
  // eslint-disable-next-line class-methods-use-this
  get name() {
    throw new Error('StorageAdapter.name is not implemented');
  }

  // eslint-disable-next-line no-unused-vars, class-methods-use-this
  async save({ userId, buffer, extension }) {
    throw new Error('StorageAdapter.save is not implemented');
  }

  // eslint-disable-next-line no-unused-vars, class-methods-use-this
  async createReadStream(key) {
    throw new Error('StorageAdapter.createReadStream is not implemented');
  }

  // eslint-disable-next-line no-unused-vars, class-methods-use-this
  async stat(key) {
    throw new Error('StorageAdapter.stat is not implemented');
  }

  // eslint-disable-next-line no-unused-vars, class-methods-use-this
  async remove(key) {
    throw new Error('StorageAdapter.remove is not implemented');
  }

  // eslint-disable-next-line no-unused-vars, class-methods-use-this
  async removeUserScope(userId) {
    throw new Error('StorageAdapter.removeUserScope is not implemented');
  }
}

module.exports = StorageAdapter;
