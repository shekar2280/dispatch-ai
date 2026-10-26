import { spawnSync } from 'node:child_process';
import { smokeEnvironment } from './smoke-environment.mjs';

const result = spawnSync(process.execPath, ['node_modules/next/dist/bin/next', 'build'], {
  stdio: 'inherit',
  env: smokeEnvironment,
});

process.exit(result.status ?? 1);
