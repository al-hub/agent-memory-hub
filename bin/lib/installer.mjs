import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

export const AGENTS = ['codex', 'claude', 'gemini'];
export const MANAGED_HOOK_NAME = 'agent-memory-hub';

function quoteShell(value) {
  const s = String(value);
  return `'${s.replaceAll("'", `'"'"'`)}'`;
}

export function managedHook(agent, runtimeDir) {
  if (!AGENTS.includes(agent)) throw new Error(`Unsupported agent: ${agent}`);
  const script = path.join(runtimeDir, 'scripts', 'session_start_hook.py');
  return {
    matcher: '',
    hooks: [
      {
        name: MANAGED_HOOK_NAME,
        type: 'command',
        command: `python3 ${quoteShell(script)} --agent ${agent}`,
        timeout: 10000,
      },
    ],
  };
}

function isManagedGroup(group) {
  return Array.isArray(group?.hooks) && group.hooks.some(h => h?.name === MANAGED_HOOK_NAME);
}

export function mergeHookConfig(existing, managedGroup) {
  const out = structuredClone(existing && typeof existing === 'object' ? existing : {});
  out.hooks = out.hooks && typeof out.hooks === 'object' ? out.hooks : {};
  const current = Array.isArray(out.hooks.SessionStart) ? out.hooks.SessionStart : [];
  out.hooks.SessionStart = [...current.filter(group => !isManagedGroup(group)), managedGroup];
  return out;
}

export function removeManagedHook(existing) {
  const out = structuredClone(existing && typeof existing === 'object' ? existing : {});
  if (!out.hooks || typeof out.hooks !== 'object') return out;
  if (Array.isArray(out.hooks.SessionStart)) {
    out.hooks.SessionStart = out.hooks.SessionStart.filter(group => !isManagedGroup(group));
    if (out.hooks.SessionStart.length === 0) delete out.hooks.SessionStart;
  }
  if (Object.keys(out.hooks).length === 0) delete out.hooks;
  return out;
}

export function agentConfigPath(agent, userHome = os.homedir()) {
  if (agent === 'codex') return path.join(userHome, '.codex', 'hooks.json');
  if (agent === 'claude') return path.join(userHome, '.claude', 'settings.json');
  if (agent === 'gemini') return path.join(userHome, '.gemini', 'settings.json');
  throw new Error(`Unsupported agent: ${agent}`);
}

function readJson(file) {
  if (!fs.existsSync(file)) return {};
  const raw = fs.readFileSync(file, 'utf8').trim();
  if (!raw) return {};
  const value = JSON.parse(raw);
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`Expected JSON object in ${file}`);
  }
  return value;
}

function atomicWriteJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.agent-memory-hub.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  fs.renameSync(tmp, file);
}

function backupOnce(file) {
  if (!fs.existsSync(file)) return null;
  const backup = `${file}.agent-memory-hub.bak`;
  if (!fs.existsSync(backup)) fs.copyFileSync(file, backup);
  return backup;
}

export function installRuntime(packageRoot, memoryHome) {
  const runtime = path.join(memoryHome, 'runtime');
  const staging = path.join(memoryHome, `.runtime-staging-${process.pid}`);
  fs.mkdirSync(memoryHome, { recursive: true });
  fs.rmSync(staging, { recursive: true, force: true });
  fs.mkdirSync(staging, { recursive: true });

  for (const dir of ['scripts', 'src']) {
    const source = path.join(packageRoot, dir);
    if (!fs.existsSync(source)) throw new Error(`Package is missing ${dir}/`);
    fs.cpSync(source, path.join(staging, dir), { recursive: true });
  }
  for (const file of ['SKILL.md', 'README.md', 'pyproject.toml']) {
    const source = path.join(packageRoot, file);
    if (fs.existsSync(source)) fs.copyFileSync(source, path.join(staging, file));
  }

  fs.rmSync(runtime, { recursive: true, force: true });
  fs.renameSync(staging, runtime);
  return runtime;
}

export function configureAgent(agent, runtimeDir, userHome = os.homedir()) {
  const file = agentConfigPath(agent, userHome);
  const existing = readJson(file);
  const merged = mergeHookConfig(existing, managedHook(agent, runtimeDir));
  backupOnce(file);
  atomicWriteJson(file, merged);
  return file;
}

export function unconfigureAgent(agent, userHome = os.homedir()) {
  const file = agentConfigPath(agent, userHome);
  if (!fs.existsSync(file)) return { file, changed: false };
  const existing = readJson(file);
  const cleaned = removeManagedHook(existing);
  if (JSON.stringify(existing) === JSON.stringify(cleaned)) return { file, changed: false };
  backupOnce(file);
  atomicWriteJson(file, cleaned);
  return { file, changed: true };
}

export function initStore(runtimeDir, memoryHome) {
  const script = path.join(runtimeDir, 'scripts', 'memory_hub.py');
  const result = spawnSync('python3', [script, '--home', memoryHome, 'init'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.status !== 0) {
    throw new Error(`memory-hub init failed: ${(result.stderr || result.stdout || '').trim()}`);
  }
  return (result.stdout || '').trim();
}

export function installSkill({ packageRoot, skipSkill = false } = {}) {
  if (skipSkill) return { skipped: true };
  const result = spawnSync('npx', ['-y', 'skills@latest', 'add', 'al-hub/agent-memory-hub', '-g', '-y'], {
    cwd: packageRoot,
    encoding: 'utf8',
    stdio: ['inherit', 'pipe', 'pipe'],
  });
  if (result.status !== 0) {
    throw new Error(`Agent Skill install failed: ${(result.stderr || result.stdout || '').trim()}`);
  }
  return { skipped: false, output: (result.stdout || '').trim() };
}

export function uninstallSkill({ packageRoot, skipSkill = false } = {}) {
  if (skipSkill) return { skipped: true };
  // skills CLI does not guarantee a stable remove command across versions.
  // Keep hook/runtime uninstall deterministic; users can remove the skill with their
  // Agent Skills manager if their installed CLI exposes removal.
  return { skipped: true, reason: 'skill removal left to Agent Skills manager' };
}
