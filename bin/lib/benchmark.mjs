import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

export function resolveBenchmarkConfig(raw = {}, cwd = process.cwd()) {
  const quick = Boolean(raw.quick);
  return {
    sizes: raw.sizes ?? (quick ? '1000,10000' : '1000,10000,50000,100000'),
    warmup: raw.warmup ?? (quick ? 1 : 5),
    iterations: raw.iterations ?? (quick ? 5 : 30),
    subprocessIterations: raw.subprocessIterations ?? (quick ? 3 : 10),
    output: path.resolve(cwd, raw.output ?? 'agent-memory-hub-benchmark.json'),
  };
}

export function buildBenchmarkArgs(packageRoot, config) {
  return [
    path.join(packageRoot, 'benchmarks', 'machine_benchmark.py'),
    '--sizes', String(config.sizes),
    '--warmup', String(config.warmup),
    '--iterations', String(config.iterations),
    '--subprocess-iterations', String(config.subprocessIterations),
    '--output', config.output,
  ];
}

function pythonVersion(command) {
  const result = spawnSync(command, ['-c', 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")'], {
    encoding: 'utf8',
  });
  if (result.status !== 0) return null;
  const version = result.stdout.trim();
  const [major, minor] = version.split('.').map(Number);
  if (major > 3 || (major === 3 && minor >= 10)) return version;
  return null;
}

export function findPython() {
  const candidates = [];
  if (process.env.PYTHON) candidates.push(process.env.PYTHON);
  candidates.push('python3', 'python');
  for (const candidate of [...new Set(candidates)]) {
    if (pythonVersion(candidate)) return candidate;
  }
  throw new Error('Python 3.10+ is required for benchmark');
}

export function runBenchmark({ packageRoot, rawOptions = {}, cwd = process.cwd() }) {
  const config = resolveBenchmarkConfig(rawOptions, cwd);
  const python = findPython();
  fs.mkdirSync(path.dirname(config.output), { recursive: true });

  console.log('agent-memory-hub: practical machine benchmark');
  console.log(`mode: ${rawOptions.quick ? 'quick' : 'full'}`);
  console.log(`tiers: ${config.sizes}`);
  console.log(`python: ${python}`);
  console.log('measurement: warm in-process core + fresh-process continuity + real SessionStart hooks');

  const result = spawnSync(python, buildBenchmarkArgs(packageRoot, config), {
    cwd,
    env: {
      ...process.env,
      AGENT_MEMORY_HUB_BENCHMARK_NODE: process.version,
      AGENT_MEMORY_HUB_BENCHMARK_HOST: os.hostname(),
    },
    stdio: 'inherit',
  });

  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`benchmark failed with exit code ${result.status}`);
  }
  console.log(`benchmark report: ${config.output}`);
  return config.output;
}
