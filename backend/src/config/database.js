'use strict';

const dns = require('dns');
const mongoose = require('mongoose');
const config = require('./env');

mongoose.set('strictQuery', true);

/**
 * Point Node's DNS resolver at specific servers (DNS_SERVERS), when set.
 *
 * A `mongodb+srv://` link is found through an SRV record. Some networks'
 * routers refuse SRV questions, and the backend then cannot start at all:
 * "querySrv ECONNREFUSED _mongodb._tcp.<cluster>" (seen on the owner's laptop,
 * 2026-10-07; Render was unaffected). This changes only Node's own resolver
 * (`dns.resolve*`, which the MongoDB driver uses for SRV) -- not the system's,
 * and not `dns.lookup`, which ordinary HTTP calls use.
 *
 * @param {string[]} servers
 * @returns {boolean} whether anything was changed
 */
function applyDnsServers(servers = config.dnsServers) {
  if (!Array.isArray(servers) || servers.length === 0) return false;
  dns.setServers(servers);
  return true;
}

/**
 * Connect to MongoDB.
 * @param {string} [uri] Optional override (used by the test harness with an in-memory server).
 */
async function connectDatabase(uri = config.mongoUri) {
  applyDnsServers();
  const connection = await mongoose.connect(uri, {
    serverSelectionTimeoutMS: 10000,
  });

  if (!config.isTest) {
    // eslint-disable-next-line no-console
    console.log(`MongoDB connected: ${connection.connection.host}`);
  }

  return connection;
}

async function disconnectDatabase() {
  await mongoose.connection.close();
}

module.exports = { connectDatabase, disconnectDatabase, applyDnsServers };
