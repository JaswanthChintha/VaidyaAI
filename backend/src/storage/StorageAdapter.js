'use strict';


class StorageAdapter {
  get name() {
    throw new Error('StorageAdapter.name is not implemented');
  }

  async save({ userId, buffer, extension }) {
    throw new Error('StorageAdapter.save is not implemented');
  }

  async createReadStream(key) {
    throw new Error('StorageAdapter.createReadStream is not implemented');
  }

  async stat(key) {
    throw new Error('StorageAdapter.stat is not implemented');
  }

  async remove(key) {
    throw new Error('StorageAdapter.remove is not implemented');
  }

  async removeUserScope(userId) {
    throw new Error('StorageAdapter.removeUserScope is not implemented');
  }
}

module.exports = StorageAdapter;
