#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  AGENTS,
  ALL_AGENTS,
  agentConfigPath,
  configureAgent,
  initStore,
  installAgyPlugin,
  installRuntime,
  installSkill,
  removeManagedHook,
  hasAgyPlugin,
  uninstallAgyPlugin,
  unconfigureAgent,
  uninstallSkill,
} from './lib/installer.mjs';
import { runBenchmark } from './lib/benchmark.mjs';

const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function parseNonNegativeInt(value, name) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`${name} must be a non-negative integer`);
  return parsed;
}

function parsePositiveInt(value, name) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) throw new Error(`${name} must be a positive integer`);
  return parsed;
}

function parseArgs(argv) {
  const command = argv[0] || 'install';
  const options = {
    command,
    agents: [...ALL_AGENTS],
    memoryHome: path.resolve(process.env.MEMCARRY_HOME || process.env.AGENT_MEMORY_HUB_HOME || path.join(os.homedir(), '.memcarry')),
    userHome: os.homedir(),
    skipSkill: false,
    benchmark: {
      quick: false,
      sizes: null,
      warmup: null,
      iterations: null,
      subprocessIterations: null,
      output: null,
    },
  };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--no-skill') options.skipSkill = true;
    else if (arg === '--home') options.memoryHome = path.resolve(argv[++i]);
    else if (arg === '--user-home') options.userHome = path.resolve(argv[++i]);
    else if (arg === '--agents') {
      const value = argv[++i];
      options.agents = value === 'all' ? [...ALL_AGENTS] : value.split(',').map(x => x.trim()).filter(Boolean);
    } else if (arg === '--quick') options.benchmark.quick = true;
    else if (arg === '--sizes') options.benchmark.sizes = argv[++i];
    else if (arg === '--warmup') options.benchmark.warmup = parseNonNegativeInt(argv[++i], '--warmup');
    else if (arg === '--iterations') options.benchmark.iterations = parsePositiveInt(argv[++i], '--iterations');
    else if (arg === '--subprocess-iterations') options.benchmark.subprocessIterations = parsePositiveInt(argv[++i], '--subprocess-iterations');
    else if (arg === '--output') options.benchmark.output = argv[++i];
    else if (arg === '--help' || arg === '-h') options.command = 'help';
    else throw new Error(`Unknown option: ${arg}`);
  }
  for (const agent of options.agents) {
    if (!ALL_AGENTS.includes(agent)) throw new Error(`Unsupported agent: ${agent}`);
  }
  return options;
}

function help() {
  return `memcarry

Usage:
  memcarry install [--agents all|codex,claude,gemini,agy] [--home PATH] [--no-skill]
  memcarry uninstall [--agents all|codex,claude,gemini,agy] [--home PATH] [--no-skill]
  memcarry status [--agents all|codex,claude,gemini,agy] [--home PATH]
  memcarry benchmark [--quick] [--sizes LIST] [--warmup N] [--iterations N]\
 [--subprocess-iterations N] [--output PATH] [--home PATH]

Benchmark defaults:
  sizes: 1000,10000,50000,100000
  warm core: 5 warmups / 30 iterations
  fresh-process + hook: 10 measured iterations
  output: ./memcarry-benchmark.json

Quick benchmark:
  memcarry benchmark --quick

Current GitHub-backed npx form (npm 12+ requires explicit git opt-in):
  npx --allow-git=all -y github:al-hub/memcarry benchmark

After npm publication:
  npx -y @al-hub/memcarry@latest benchmark
`;
}

function readJsonSafe(file) {
  try {
    if (!fs.existsSync(file)) return {};
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return {};
  }
}

function hasManagedHook(file, runtime) {
  const config = readJsonSafe(file);
  const cleaned = removeManagedHook(config, runtime);
  return JSON.stringify(config) !== JSON.stringify(cleaned);
}

function install(options) {
  console.log('memcarry: installing shared continuity runtime');
  installSkill({ packageRoot: PACKAGE_ROOT, skipSkill: options.skipSkill });
  const runtime = installRuntime(PACKAGE_ROOT, options.memoryHome);
  const initOutput = initStore(runtime, options.memoryHome);
  if (initOutput) console.log(initOutput);

  for (const agent of options.agents) {
    if (agent === 'agy') {
      const plugin = installAgyPlugin({ packageRoot: PACKAGE_ROOT, runtimeDir: runtime, memoryHome: options.memoryHome, userHome: options.userHome });
      console.log(`configured agy: ${plugin}`);
    } else {
      const file = configureAgent(agent, runtime, options.userHome);
      console.log(`configured ${agent}: ${file}`);
    }
  }
  console.log(`runtime: ${runtime}`);
  console.log('memory data is kept outside runtime and survives upgrades.');
}

function uninstall(options) {
  console.log('memcarry: removing managed SessionStart hooks');
  for (const agent of options.agents) {
    if (agent === 'agy') {
      const result = uninstallAgyPlugin({ userHome: options.userHome });
      console.log(`${result.changed ? 'updated' : 'unchanged'} agy: ${result.pluginDir}`);
    } else {
      const result = unconfigureAgent(agent, options.userHome, path.join(options.memoryHome, 'runtime'));
      console.log(`${result.changed ? 'updated' : 'unchanged'} ${agent}: ${result.file}`);
    }
  }
  uninstallSkill({ packageRoot: PACKAGE_ROOT, skipSkill: options.skipSkill });
  const runtime = path.join(options.memoryHome, 'runtime');
  fs.rmSync(runtime, { recursive: true, force: true });
  console.log(`removed runtime: ${runtime}`);
  console.log(`preserved memory data: ${options.memoryHome}`);
}

function status(options) {
  const runtime = path.join(options.memoryHome, 'runtime');
  console.log(`runtime: ${fs.existsSync(runtime) ? 'installed' : 'missing'} (${runtime})`);
  for (const agent of options.agents) {
    if (agent === 'agy') {
      const plugin = path.join(options.userHome, '.gemini', 'antigravity-cli', 'plugins', 'memcarry');
      console.log(`agy: ${hasAgyPlugin(options.userHome) ? 'hooked' : 'not hooked'} (${plugin})`);
    } else {
      const file = agentConfigPath(agent, options.userHome);
      console.log(`${agent}: ${hasManagedHook(file, runtime) ? 'hooked' : 'not hooked'} (${file})`);
    }
  }
  const db = path.join(options.memoryHome, 'memory.db');
  console.log(`store: ${fs.existsSync(db) ? 'initialized' : 'not initialized'} (${db})`);
}

try {
  const options = parseArgs(process.argv.slice(2));
  if (options.command === 'help') console.log(help());
  else if (options.command === 'install') install(options);
  else if (options.command === 'uninstall') uninstall(options);
  else if (options.command === 'status') status(options);
  else if (options.command === 'benchmark') {
    runBenchmark({
      packageRoot: PACKAGE_ROOT,
      memoryHome: options.memoryHome,
      rawOptions: options.benchmark,
    });
  } else throw new Error(`Unknown command: ${options.command}`);
} catch (error) {
  console.error(`memcarry: ${error.message}`);
  process.exitCode = 1;
}
