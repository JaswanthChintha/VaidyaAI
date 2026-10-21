'use strict';

const dns = require('dns');
const mongoose = require('mongoose');
const config = require('./env');

mongoose.set('strictQuery', true);

function applyDnsServers(servers = config.dnsServers) {
  if (!Array.isArray(servers) || servers.length === 0) return false;
  dns.setServers(servers);
  return true;
}

async function connectDatabase(uri = config.mongoUri) {
  applyDnsServers();
  const connection = await mongoose.connect(uri, {
    serverSelectionTimeoutMS: 10000,
  });

  if (!config.isTest) {
    console.log(`MongoDB connected: ${connection.connection.host}`);
  }

  return connection;
}

async function disconnectDatabase() {
  await mongoose.connection.close();
}

module.exports = { connectDatabase, disconnectDatabase, applyDnsServers };
