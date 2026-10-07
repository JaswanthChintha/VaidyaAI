'use strict';

/**
 * DNS_SERVERS (2026-10-07). On the owner's laptop the backend could not start:
 * "querySrv ECONNREFUSED _mongodb._tcp.cluster0...". The Wi-Fi router refuses
 * the SRV question a `mongodb+srv://` link needs. With DNS_SERVERS set, Node's
 * own resolver asks those servers instead.
 */

const dns = require('dns');
const { parseDnsServers } = require('../src/config/env');
const { applyDnsServers } = require('../src/config/database');

describe('parseDnsServers', () => {
  it.each([
    [undefined, []],
    ['', []],
    ['   ', []],
    ['8.8.8.8', ['8.8.8.8']],
    [' 8.8.8.8 , 1.1.1.1 ', ['8.8.8.8', '1.1.1.1']],
    ['2001:4860:4860::8888', ['2001:4860:4860::8888']],
  ])('%j -> %j', (raw, expected) => {
    expect(parseDnsServers(raw)).toEqual(expected);
  });

  it('refuses something that is not an IP address, naming it', () => {
    expect(() => parseDnsServers('8.8.8.8,dns.google')).toThrow(/not an IP address: dns.google/);
  });
});

describe('applyDnsServers', () => {
  afterEach(() => jest.restoreAllMocks());

  it('points the resolver at the given servers', () => {
    const set = jest.spyOn(dns, 'setServers').mockImplementation(() => {});
    expect(applyDnsServers(['8.8.8.8', '1.1.1.1'])).toBe(true);
    expect(set).toHaveBeenCalledWith(['8.8.8.8', '1.1.1.1']);
  });

  it('changes nothing when none are configured -- the system DNS stays', () => {
    const set = jest.spyOn(dns, 'setServers').mockImplementation(() => {});
    expect(applyDnsServers([])).toBe(false);
    expect(applyDnsServers(undefined)).toBe(false);
    expect(set).not.toHaveBeenCalled();
  });
});
