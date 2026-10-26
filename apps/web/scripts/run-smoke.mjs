import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { setTimeout as delay } from 'node:timers/promises';
import { smokeEnvironment } from './smoke-environment.mjs';

const probe = createServer();
probe.listen(3100, '127.0.0.1');
await once(probe, 'listening');
await new Promise(resolve => probe.close(resolve));

const server = spawn(process.execPath, [
  'node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3100',
], { stdio: 'inherit', env: smokeEnvironment });
const serverExit = once(server, 'exit');
let tests;
let exitCode = 1;

const stop = () => {
  tests?.kill();
  server.kill();
};
process.once('SIGINT', stop);
process.once('SIGTERM', stop);

try {
  const deadline = Date.now() + 60_000;
  while (true) {
    if (server.exitCode !== null) throw new Error('The smoke server exited before it was ready');
    let ready = false;
    try {
      const response = await fetch('http://127.0.0.1:3100/login', { signal: AbortSignal.timeout(1_000) });
      await response.body?.cancel();
      ready = response.ok;
    } catch {
      // Retry while Next.js starts; the deadline also covers connection failures.
    }
    if (ready) break;
    if (Date.now() > deadline) throw new Error('The smoke server did not become ready within 60 seconds');
    await delay(200);
  }
  tests = spawn(process.execPath, [
    'node_modules/playwright/cli.js', 'test', '--config', 'playwright.smoke.config.ts', ...process.argv.slice(2),
  ], { stdio: 'inherit', env: smokeEnvironment });
  const [code] = await once(tests, 'exit');
  exitCode = code ?? 1;
} finally {
  stop();
  const forceStop = setTimeout(() => server.kill('SIGKILL'), 5_000);
  try {
    await serverExit;
  } finally {
    clearTimeout(forceStop);
  }
}

process.exitCode = exitCode;
