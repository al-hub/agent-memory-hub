import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

export const AGENTS = ['codex', 'claude', 'gemini'];
export const ALL_AGENTS = [...AGENTS, 'agy'];
export const MANAGED_HOOK_NAME = 'memcarry';

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
        command: `python3 ${quoteShell(script)} --home ${quoteShell(path.dirname(runtimeDir))} --agent ${agent}`,
      },
    ],
  };
}

function agyPluginDir(userHome = os.homedir()) {
  return path.join(userHome, '.gemini', 'antigravity-cli', 'plugins', 'memcarry');
}

export function installAgyPlugin({ packageRoot, runtimeDir, memoryHome, userHome = os.homedir() }) {
  const pluginDir = agyPluginDir(userHome);
  const staging = `${pluginDir}.staging-${process.pid}`;
  fs.rmSync(staging, { recursive: true, force: true });
  fs.mkdirSync(path.join(staging, 'skills', 'memcarry'), { recursive: true });
  fs.writeFileSync(path.join(staging, 'plugin.json'), `${JSON.stringify({
    $schema: 'https://antigravity.google/schemas/v1/plugin.json',
    name: 'memcarry',
    description: 'Project memory and continuity for Antigravity CLI',
  }, null, 2)}\n`);
  const command = `python3 ${quoteShell(path.join(runtimeDir, 'scripts', 'antigravity_hook.py'))} --home ${quoteShell(memoryHome)} --event pre-invocation`;
  fs.writeFileSync(path.join(staging, 'hooks.json'), `${JSON.stringify({
    memcarry: { PreInvocation: [{ type: 'command', command, timeout: 10 }] },
  }, null, 2)}\n`);
  const skill = path.join(packageRoot, 'SKILL.md');
  if (fs.existsSync(skill)) fs.copyFileSync(skill, path.join(staging, 'skills', 'memcarry', 'SKILL.md'));
  fs.mkdirSync(path.dirname(pluginDir), { recursive: true });
  fs.rmSync(pluginDir, { recursive: true, force: true });
  fs.renameSync(staging, pluginDir);
  return pluginDir;
}

export function uninstallAgyPlugin({ userHome = os.homedir() } = {}) {
  const pluginDir = agyPluginDir(userHome);
  const manifest = path.join(pluginDir, 'plugin.json');
  if (!fs.existsSync(manifest)) return { pluginDir, changed: false };
  try {
    if (readJson(manifest).name !== 'memcarry') return { pluginDir, changed: false };
  } catch { return { pluginDir, changed: false }; }
  fs.rmSync(pluginDir, { recursive: true, force: true });
  return { pluginDir, changed: true };
}

export function hasAgyPlugin(userHome = os.homedir()) {
  try { return readJson(path.join(agyPluginDir(userHome), 'plugin.json')).name === 'memcarry'; }
  catch { return false; }
}

function isManagedHook(hook, legacyRuntime) {
  if (hook?.name === MANAGED_HOOK_NAME) return true;
  // Only adopt the exact old al-hub command in the explicitly selected runtime.
  // A similarly named hook belonging to another project is not ours to remove.
  return Boolean(legacyRuntime && hook?.name === 'agent-memory-hub' &&
    AGENTS.some(agent => hook.command ===
      `python3 ${quoteShell(path.join(legacyRuntime, 'scripts', 'session_start_hook.py'))} --agent ${agent}`));
}

export function mergeHookConfig(existing, managedGroup, legacyRuntime) {
  const out = removeManagedHook(existing, legacyRuntime);
  out.hooks = out.hooks && typeof out.hooks === 'object' ? out.hooks : {};
  const current = Array.isArray(out.hooks.SessionStart) ? out.hooks.SessionStart : [];
  out.hooks.SessionStart = [...current, managedGroup];
  return out;
}

export function removeManagedHook(existing, legacyRuntime) {
  const out = structuredClone(existing && typeof existing === 'object' ? existing : {});
  if (!out.hooks || typeof out.hooks !== 'object') return out;
  if (Array.isArray(out.hooks.SessionStart)) {
    out.hooks.SessionStart = out.hooks.SessionStart.flatMap(group => {
      if (!Array.isArray(group?.hooks)) return [group];
      const hooks = group.hooks.filter(hook => !isManagedHook(hook, legacyRuntime));
      if (hooks.length === group.hooks.length) return [group];
      return hooks.length ? [{ ...group, hooks }] : [];
    });
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
  const tmp = `${file}.memcarry.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  fs.renameSync(tmp, file);
}

function backupOnce(file) {
  if (!fs.existsSync(file)) return null;
  const backup = `${file}.memcarry.bak`;
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
  const docs = path.join(packageRoot, 'docs');
  if (fs.existsSync(docs)) fs.cpSync(docs, path.join(staging, 'docs'), { recursive: true });

  fs.rmSync(runtime, { recursive: true, force: true });
  fs.renameSync(staging, runtime);
  return runtime;
}

export function configureAgent(agent, runtimeDir, userHome = os.homedir()) {
  const file = agentConfigPath(agent, userHome);
  const existing = readJson(file);
  const merged = mergeHookConfig(existing, managedHook(agent, runtimeDir), runtimeDir);
  backupOnce(file);
  atomicWriteJson(file, merged);
  return file;
}

export function unconfigureAgent(agent, userHome = os.homedir(), legacyRuntime) {
  const file = agentConfigPath(agent, userHome);
  if (!fs.existsSync(file)) return { file, changed: false };
  const existing = readJson(file);
  const cleaned = removeManagedHook(existing, legacyRuntime);
  if (JSON.stringify(existing) === JSON.stringify(cleaned)) return { file, changed: false };
  backupOnce(file);
  atomicWriteJson(file, cleaned);
  return { file, changed: true };
}

export function initStore(runtimeDir, memoryHome) {
  const script = path.join(runtimeDir, 'scripts', 'memcarry_store.py');
  const result = spawnSync('python3', [script, '--home', memoryHome, 'init'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.status !== 0) {
    throw new Error(`memcarry init failed: ${(result.stderr || result.stdout || '').trim()}`);
  }
  return (result.stdout || '').trim();
}

export function installSkill({ packageRoot, skipSkill = false } = {}) {
  if (skipSkill) return { skipped: true };
  const result = spawnSync('npx', ['-y', 'skills@latest', 'add', 'al-hub/memcarry', '-g', '-y'], {
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
  const result = spawnSync('npx', ['-y', 'skills@latest', 'remove', MANAGED_HOOK_NAME, '-g', '-y'], {
    cwd: packageRoot,
    encoding: 'utf8',
    stdio: ['inherit', 'pipe', 'pipe'],
  });
  if (result.status !== 0) {
    throw new Error(`Agent Skill removal failed: ${(result.stderr || result.stdout || '').trim()}`);
  }
  return { skipped: false, output: (result.stdout || '').trim() };
}
