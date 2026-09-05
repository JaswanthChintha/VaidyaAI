'use strict';

const request = require('supertest');
const app = require('../src/app');
const User = require('../src/models/User');
const config = require('../src/config/env');

const BASE = `${config.apiPrefix}/auth`;

const validUser = {
  name: 'Asha Patel',
  email: 'asha.patel@example.com',
  password: 'Str0ng!Passw0rd',
};

/** Register a user through the public API and return { res, tokens, user }. */
async function registerUser(overrides = {}) {
  const payload = { ...validUser, ...overrides };
  const res = await request(app).post(`${BASE}/register`).send(payload);
  return { res, payload, body: res.body };
}

/** Create a user directly in the DB with an arbitrary role (bypasses signup rules). */
async function createUserWithRole(role, overrides = {}) {
  const payload = { ...validUser, ...overrides, role };
  return User.create(payload);
}

/** Log in and return the token pair. */
async function login(email, password) {
  const res = await request(app).post(`${BASE}/login`).send({ email, password });
  return res;
}

module.exports = { app, request, BASE, validUser, registerUser, createUserWithRole, login };
