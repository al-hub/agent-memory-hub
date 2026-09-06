#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  AGENTS,
  agentConfigPath,
  configureAgent,
  initStore,
  installRuntime,
  installSkill,
  removeManagedHook,
  unconfigureAgent,
} from './lib/installer.mjs';

const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function parseArgs(argv) {
  const command = argv[0] || 'install';
  const options = {
    command,
    agents: [...AGENTS],
    memoryHome: path.join(os.homedir(), '.agent-memory-hub'),
    userHome: os.homedir(),
    skipSkill: false,
  };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--no-skill') options.skipSkill = true;
    else if (arg === '--home') options.memoryHome = path.resolve(argv[++i]);
    else if (arg === '--user-home') options.userHome = path.resolve(argv[++i]);
    else if (arg === '--agents') {
      const value = argv[++i];
      options.agents = value === 'all' ? [...AGENTS] : value.split(',').map(x => x.trim()).filter(Boolean);
    } else if (arg === '--help' || arg === '-h') options.command = 'help';
    else throw new Error(`Unknown option: ${arg}`);
  }
  for (const agent of options.agents) {
    if (!AGENTS.includes(agent)) throw new Error(`Unsupported agent: ${agent}`);
  }
  return options;
}

function help() {
  return `agent-memory-hub

Usage:
  agent-memory-hub install [--agents all|codex,claude,gemini] [--home PATH] [--no-skill]
  agent-memory-hub uninstall [--agents all|codex,claude,gemini] [--home PATH]
  agent-memory-hub status [--agents all|codex,claude,gemini] [--home PATH]

Current GitHub-backed npx form:
  npx -y github:al-hub/agent-memory-hub install

After npm publication:
  npx -y @al-hub/agent-memory-hub@latest install
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

function hasManagedHook(file) {
  const config = readJsonSafe(file);
  const cleaned = removeManagedHook(config);
  return JSON.stringify(config) !== JSON.stringify(cleaned);
}

function install(options) {
  console.log('agent-memory-hub: installing shared continuity runtime');
  installSkill({ packageRoot: PACKAGE_ROOT, skipSkill: options.skipSkill });
  const runtime = installRuntime(PACKAGE_ROOT, options.memoryHome);
  const initOutput = initStore(runtime, options.memoryHome);
  if (initOutput) console.log(initOutput);

  for (const agent of options.agents) {
    const file = configureAgent(agent, runtime, options.userHome);
    console.log(`configured ${agent}: ${file}`);
  }
  console.log(`runtime: ${runtime}`);
  console.log('memory data is kept outside runtime and survives upgrades.');
}

function uninstall(options) {
  console.log('agent-memory-hub: removing managed SessionStart hooks');
  for (const agent of options.agents) {
    const result = unconfigureAgent(agent, options.userHome);
    console.log(`${result.changed ? 'updated' : 'unchanged'} ${agent}: ${result.file}`);
  }
  const runtime = path.join(options.memoryHome, 'runtime');
  fs.rmSync(runtime, { recursive: true, force: true });
  console.log(`removed runtime: ${runtime}`);
  console.log(`preserved memory data: ${options.memoryHome}`);
}

function status(options) {
  const runtime = path.join(options.memoryHome, 'runtime');
  console.log(`runtime: ${fs.existsSync(runtime) ? 'installed' : 'missing'} (${runtime})`);
  for (const agent of options.agents) {
    const file = agentConfigPath(agent, options.userHome);
    console.log(`${agent}: ${hasManagedHook(file) ? 'hooked' : 'not hooked'} (${file})`);
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
  else throw new Error(`Unknown command: ${options.command}`);
} catch (error) {
  console.error(`agent-memory-hub: ${error.message}`);
  process.exitCode = 1;
}
