'use strict';

const assert = require('node:assert/strict');
const net = require('node:net');
const test = require('node:test');

const {
  DEFAULT_API_PORT,
  findAvailablePort,
  parsePort,
  probePort,
} = require('../electron/api-port.cjs');

test('uses 8000 as the default starting port', () => {
  assert.equal(DEFAULT_API_PORT, 8000);
  assert.equal(parsePort(undefined), null);
  assert.equal(parsePort('  '), null);
});

test('rejects invalid configured ports', () => {
  assert.throws(() => parsePort('abc'), /Invalid API port/);
  assert.throws(() => parsePort(0), /Invalid API port/);
  assert.throws(() => parsePort(65536), /Invalid API port/);
});

test('keeps an explicitly requested available port', async () => {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, '0.0.0.0', resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));

  assert.equal(await findAvailablePort(String(port)), port);
});

test('reports an explicitly requested occupied port', async () => {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, '0.0.0.0', resolve));
  const port = server.address().port;

  await assert.rejects(
    findAvailablePort(port),
    new RegExp(`API port ${port} is unavailable`),
  );
  await new Promise((resolve) => server.close(resolve));
});

test('falls back when the scan starting port is occupied', async () => {
  const first = net.createServer();
  await new Promise((resolve) => first.listen(0, '0.0.0.0', resolve));
  const start = first.address().port;

  try {
    const result = await findAvailablePort(undefined, { start, attempts: 5 });
    assert.ok(result > start);
    assert.equal((await probePort(result)).available, true);
  } finally {
    await new Promise((resolve) => first.close(resolve));
  }
});
