'use strict';

const net = require('net');

const DEFAULT_API_PORT = 8000;
const DEFAULT_SCAN_ATTEMPTS = 50;

function parsePort(value) {
  if (value === undefined || value === null || String(value).trim() === '') {
    return null;
  }

  const raw = String(value).trim();
  if (!/^\d+$/.test(raw)) {
    throw new Error(`Invalid API port "${value}". Use an integer between 1 and 65535.`);
  }

  const port = Number(raw);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535) {
    throw new Error(`Invalid API port "${value}". Use an integer between 1 and 65535.`);
  }
  return port;
}

function probePort(port, host = '0.0.0.0') {
  return new Promise((resolve) => {
    const server = net.createServer();
    let settled = false;
    const finish = (available, error = null) => {
      if (settled) return;
      settled = true;
      resolve({ available, error });
    };

    server.once('error', (error) => finish(false, error));
    server.listen({ host, port, exclusive: true }, () => {
      server.close((error) => finish(!error, error));
    });
  });
}

async function findAvailablePort(requested, options = {}) {
  const explicit = requested !== undefined && requested !== null
    && String(requested).trim() !== '';
  const host = options.host || '0.0.0.0';

  if (explicit) {
    const port = parsePort(requested);
    const result = await probePort(port, host);
    if (!result.available) {
      const detail = result.error && result.error.message ? `: ${result.error.message}` : '';
      throw new Error(`API port ${port} is unavailable${detail}`);
    }
    return port;
  }

  const start = options.start === undefined ? DEFAULT_API_PORT : parsePort(options.start);
  if (start === null) {
    throw new Error('API port scan start must be an integer between 1 and 65535.');
  }
  const attempts = options.attempts === undefined ? DEFAULT_SCAN_ATTEMPTS : options.attempts;
  if (!Number.isSafeInteger(attempts) || attempts < 1) {
    throw new Error('API port scan attempts must be a positive integer.');
  }

  for (let offset = 0; offset < attempts; offset += 1) {
    const port = start + offset;
    if (port > 65535) break;
    const result = await probePort(port, host);
    if (result.available) return port;
  }

  const end = Math.min(65535, start + attempts - 1);
  throw new Error(`No available API port found between ${start} and ${end}.`);
}

module.exports = {
  DEFAULT_API_PORT,
  DEFAULT_SCAN_ATTEMPTS,
  findAvailablePort,
  parsePort,
  probePort,
};
