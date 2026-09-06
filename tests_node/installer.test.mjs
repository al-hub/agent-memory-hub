import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  managedHook,
  mergeHookConfig,
  removeManagedHook,
  installRuntime,
} from '../bin/lib/installer.mjs';

const agents = ['codex', 'claude', 'gemini'];

test('managed hook uses persistent runtime path and agent profile', () => {
  const runtime = '/home/me/.agent-memory-hub/runtime';
  for (const agent of agents) {
    const hook = managedHook(agent, runtime);
    assert.equal(hook.matcher, '');
    assert.equal(hook.hooks.length, 1);
    assert.equal(hook.hooks[0].name, 'agent-memory-hub');
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
  assert.equal(merged.hooks.SessionStart.filter(x => x.hooks?.some(h => h.name === 'agent-memory-hub')).length, 1);
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
  const td = fs.mkdtempSync(path.join(os.tmpdir(), 'amh-node-'));
  const source = path.join(td, 'pkg');
  const home = path.join(td, 'home');
  fs.mkdirSync(path.join(source, 'scripts'), { recursive: true });
  fs.mkdirSync(path.join(source, 'src', 'agent_memory_hub'), { recursive: true });
  fs.writeFileSync(path.join(source, 'scripts', 'session_start_hook.py'), 'print(1)');
  fs.writeFileSync(path.join(source, 'src', 'agent_memory_hub', '__init__.py'), '');
  fs.mkdirSync(home, { recursive: true });
  fs.writeFileSync(path.join(home, 'memory.db'), 'keep');
  fs.mkdirSync(path.join(home, 'runtime'), { recursive: true });
  fs.writeFileSync(path.join(home, 'runtime', 'old.txt'), 'old');

  installRuntime(source, home);

  assert.equal(fs.readFileSync(path.join(home, 'memory.db'), 'utf8'), 'keep');
  assert.ok(fs.existsSync(path.join(home, 'runtime', 'scripts', 'session_start_hook.py')));
  assert.ok(!fs.existsSync(path.join(home, 'runtime', 'old.txt')));
});
