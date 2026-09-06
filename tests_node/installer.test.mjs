import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  managedHook,
  installAgyPlugin,
  uninstallAgyPlugin,
  hasAgyPlugin,
  mergeHookConfig,
  removeManagedHook,
  installRuntime,
} from '../bin/lib/installer.mjs';

const agents = ['codex', 'claude', 'gemini'];

test('AGY plugin installs its hook and skill in Antigravity config', () => {
  const td = fs.mkdtempSync(path.join(os.tmpdir(), 'memcarry-agy-'));
  const source = path.join(td, 'pkg');
  const userHome = path.join(td, 'user');
  const memoryHome = path.join(td, 'memory');
  fs.mkdirSync(source, { recursive: true });
  fs.writeFileSync(path.join(source, 'SKILL.md'), '# Memcarry');
  const runtime = path.join(memoryHome, 'runtime');
  const plugin = installAgyPlugin({ packageRoot: source, runtimeDir: runtime, memoryHome, userHome });
  assert.equal(hasAgyPlugin(userHome), true);
  assert.equal(JSON.parse(fs.readFileSync(path.join(plugin, 'plugin.json'), 'utf8')).name, 'memcarry');
  const hooks = JSON.parse(fs.readFileSync(path.join(plugin, 'hooks.json'), 'utf8'));
  assert.equal(hooks.memcarry.PreInvocation[0].type, 'command');
  assert.match(hooks.memcarry.PreInvocation[0].command, /antigravity_hook\.py/);
  assert.equal(fs.readFileSync(path.join(plugin, 'skills', 'memcarry', 'SKILL.md'), 'utf8'), '# Memcarry');
  const removed = uninstallAgyPlugin({ userHome });
  assert.equal(removed.changed, true);
  assert.equal(hasAgyPlugin(userHome), false);
});

test('custom store path is passed to every installed hook', () => {
  const runtime = "/tmp/memory with 'quote/runtime";
  for (const agent of agents) {
    assert.ok(managedHook(agent, runtime).hooks[0].command.includes('--home '));
  }
});

test('removing a managed hook preserves neighbours in the same group', () => {
  const group = managedHook('codex', '/runtime');
  group.hooks.push({ name: 'other', type: 'command', command: 'echo keep' });
  const cleaned = removeManagedHook({ hooks: { SessionStart: [group] } });
  assert.equal(cleaned.hooks.SessionStart[0].hooks.length, 1);
  assert.equal(cleaned.hooks.SessionStart[0].hooks[0].name, 'other');
});

test('explicit legacy runtime upgrade replaces only the matching old hook', () => {
  const legacy = { name: 'agent-memory-hub', type: 'command', command: "python3 '/old/runtime/scripts/session_start_hook.py' --agent codex" };
  const foreign = { name: 'agent-memory-hub', type: 'command', command: 'memory hook startup' };
  const existing = { hooks: { SessionStart: [{ matcher: '', hooks: [legacy, foreign] }] } };
  const merged = mergeHookConfig(existing, managedHook('codex', '/old/runtime'), '/old/runtime');
  const hooks = merged.hooks.SessionStart.flatMap(group => group.hooks);
  assert.deepEqual(hooks.filter(hook => hook.name === 'agent-memory-hub'), [foreign]);
  assert.equal(hooks.filter(hook => hook.name === 'memcarry').length, 1);
  assert.equal(existing.hooks.SessionStart[0].hooks.length, 2);
  assert.deepEqual(removeManagedHook(existing), existing);
});

test('managed hook uses persistent runtime path and agent profile', () => {
  const runtime = '/home/me/.memcarry/runtime';
  for (const agent of agents) {
    const hook = managedHook(agent, runtime);
    assert.equal(hook.matcher, '');
    assert.equal(hook.hooks.length, 1);
    assert.equal(hook.hooks[0].name, 'memcarry');
    assert.match(hook.hooks[0].command, /session_start_hook\.py/);
    assert.match(hook.hooks[0].command, new RegExp(`--agent ${agent}$`));
    assert.ok(hook.hooks[0].command.includes(runtime));
  }
});

test('merge preserves unrelated settings and hooks', () => {
  const existing = {
    theme: 'dark',
    hooks: {
      SessionStart: [{ matcher: 'startup', hooks: [{ name: 'other', type: 'command', command: 'echo hi' }] }],
      BeforeTool: [{ matcher: '*', hooks: [{ name: 'guard', type: 'command', command: 'guard' }] }],
    },
  };
  const merged = mergeHookConfig(existing, managedHook('claude', '/runtime'));
  assert.equal(merged.theme, 'dark');
  assert.equal(merged.hooks.BeforeTool.length, 1);
  assert.equal(merged.hooks.SessionStart.length, 2);
  assert.equal(merged.hooks.SessionStart.filter(x => x.hooks?.some(h => h.name === 'memcarry')).length, 1);
});

test('merge is idempotent and replaces only our prior hook', () => {
  const first = mergeHookConfig({}, managedHook('gemini', '/old/runtime'));
  const second = mergeHookConfig(first, managedHook('gemini', '/new/runtime'));
  assert.equal(second.hooks.SessionStart.length, 1);
  assert.match(second.hooks.SessionStart[0].hooks[0].command, /\/new\/runtime/);
});

test('uninstall removes only managed hook and retains unrelated config', () => {
  const existing = mergeHookConfig(
    { hooks: { SessionStart: [{ matcher: 'startup', hooks: [{ name: 'other', type: 'command', command: 'other' }] }] }, x: 1 },
    managedHook('codex', '/runtime'),
  );
  const cleaned = removeManagedHook(existing);
  assert.equal(cleaned.x, 1);
  assert.equal(cleaned.hooks.SessionStart.length, 1);
  assert.equal(cleaned.hooks.SessionStart[0].hooks[0].name, 'other');
});

test('runtime copy replaces runtime without touching sibling memory data', () => {
  const td = fs.mkdtempSync(path.join(os.tmpdir(), 'memcarry-node-'));
  const source = path.join(td, 'pkg');
  const home = path.join(td, 'home');
  fs.mkdirSync(path.join(source, 'scripts'), { recursive: true });
  fs.mkdirSync(path.join(source, 'src', 'memcarry'), { recursive: true });
  fs.writeFileSync(path.join(source, 'scripts', 'session_start_hook.py'), 'print(1)');
  fs.writeFileSync(path.join(source, 'src', 'memcarry', '__init__.py'), '');
  fs.mkdirSync(home, { recursive: true });
  fs.writeFileSync(path.join(home, 'memory.db'), 'keep');
  fs.mkdirSync(path.join(home, 'runtime'), { recursive: true });
  fs.writeFileSync(path.join(home, 'runtime', 'old.txt'), 'old');

  installRuntime(source, home);

  assert.equal(fs.readFileSync(path.join(home, 'memory.db'), 'utf8'), 'keep');
  assert.ok(fs.existsSync(path.join(home, 'runtime', 'scripts', 'session_start_hook.py')));
  assert.ok(!fs.existsSync(path.join(home, 'runtime', 'old.txt')));
});
