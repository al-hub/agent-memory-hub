import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const BIN = path.join(ROOT, 'bin', 'memcarry.mjs');

function run(args, env = process.env) {
  return spawnSync(process.execPath, [BIN, ...args], { encoding: 'utf8', env });
}

test('store selection respects explicit home, new environment, then legacy environment', () => {
  const env = { ...process.env, MEMCARRY_HOME: '/tmp/memcarry-new-store', AGENT_MEMORY_HUB_HOME: '/tmp/memcarry-legacy-store' };
  assert.match(run(['status'], env).stdout, /memcarry-new-store/);
  assert.match(run(['status', '--home', '/tmp/memcarry-explicit-store'], env).stdout, /memcarry-explicit-store/);
  delete env.MEMCARRY_HOME;
  assert.match(run(['status'], env).stdout, /memcarry-legacy-store/);
});

test('installed hook actually reads its custom store, including shell-sensitive paths', () => {
  const td = fs.mkdtempSync(path.join(os.tmpdir(), 'memcarry-hook-'));
  try {
    const userHome = path.join(td, 'user');
    const memoryHome = path.join(td, "memory with 'quote");
    const repo = path.join(td, 'repo');
    fs.mkdirSync(repo);
    for (const args of [['init', '-b', 'main'], ['remote', 'add', 'origin', 'https://github.com/example/custom-home.git']]) {
      const result = spawnSync('git', args, { cwd: repo, encoding: 'utf8' });
      assert.equal(result.status, 0, result.stderr);
    }
    const result = run(['install', '--no-skill', '--home', memoryHome, '--user-home', userHome]);
    assert.equal(result.status, 0, result.stderr);
    const writer = spawnSync('python3', [path.join(memoryHome, 'runtime/scripts/memcarry_store.py'), '--home', memoryHome,
      'add', 'Custom store verified marker', '--type', 'decision', '--status', 'confirmed',
      '--scope', 'repository', '--scope-ref', 'github.com/example/custom-home'], { encoding: 'utf8' });
    assert.equal(writer.status, 0, writer.stderr);
    for (const [agent, file] of [['codex', '.codex/hooks.json'], ['claude', '.claude/settings.json'], ['gemini', '.gemini/settings.json']]) {
      const config = JSON.parse(fs.readFileSync(path.join(userHome, file), 'utf8'));
      const command = config.hooks.SessionStart[0].hooks[0].command;
      const hook = spawnSync('/bin/sh', ['-c', command], { encoding: 'utf8',
        input: JSON.stringify({ hook_event_name: 'SessionStart', cwd: repo, session_id: agent, source: 'startup' }),
        env: { ...process.env, MEMCARRY_HOME: path.join(td, 'wrong') } });
      assert.equal(hook.status, 0, hook.stderr);
      assert.equal(hook.stderr, '');
      assert.match(JSON.parse(hook.stdout).hookSpecificOutput.additionalContext, /Custom store verified marker/);
    }
    assert.ok(fs.existsSync(path.join(memoryHome, 'runtime/docs/USAGE-SCENARIOS.md')));
  } finally {
    fs.rmSync(td, { recursive: true, force: true });
  }
});

test('install status uninstall is idempotent and preserves unrelated settings/data', () => {
  const td = fs.mkdtempSync(path.join(os.tmpdir(), 'memcarry-cli-'));
  const userHome = path.join(td, 'user');
  const memoryHome = path.join(td, 'memory');
  const claudeSettings = path.join(userHome, '.claude', 'settings.json');
  fs.mkdirSync(path.dirname(claudeSettings), { recursive: true });
  fs.writeFileSync(
    claudeSettings,
    JSON.stringify({ theme: 'dark', hooks: { SessionStart: [{ matcher: 'startup', hooks: [{ name: 'other', type: 'command', command: 'echo other' }] }] } }, null, 2),
  );

  const common = ['--no-skill', '--home', memoryHome, '--user-home', userHome, '--agents', 'codex,claude,gemini'];
  let result = run(['install', ...common]);
  assert.equal(result.status, 0, result.stderr);
  result = run(['install', ...common]);
  assert.equal(result.status, 0, result.stderr);

  const claude = JSON.parse(fs.readFileSync(claudeSettings, 'utf8'));
  assert.equal(claude.theme, 'dark');
  assert.equal(claude.hooks.SessionStart.filter(g => g.hooks?.some(h => h.name === 'memcarry')).length, 1);
  assert.equal(claude.hooks.SessionStart.filter(g => g.hooks?.some(h => h.name === 'other')).length, 1);
  assert.ok(fs.existsSync(`${claudeSettings}.memcarry.bak`));
  assert.ok(fs.existsSync(path.join(memoryHome, 'runtime', 'scripts', 'session_start_hook.py')));
  assert.ok(fs.existsSync(path.join(memoryHome, 'memory.db')));

  result = run(['status', '--home', memoryHome, '--user-home', userHome, '--agents', 'all']);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /runtime: installed/);
  assert.match(result.stdout, /codex: hooked/);
  assert.match(result.stdout, /claude: hooked/);
  assert.match(result.stdout, /gemini: hooked/);

  fs.writeFileSync(path.join(memoryHome, 'sentinel.txt'), 'keep');
  result = run(['uninstall', '--no-skill', '--home', memoryHome, '--user-home', userHome, '--agents', 'all']);
  assert.equal(result.status, 0, result.stderr);
  assert.ok(!fs.existsSync(path.join(memoryHome, 'runtime')));
  assert.equal(fs.readFileSync(path.join(memoryHome, 'sentinel.txt'), 'utf8'), 'keep');
  assert.ok(fs.existsSync(path.join(memoryHome, 'memory.db')));

  const cleaned = JSON.parse(fs.readFileSync(claudeSettings, 'utf8'));
  assert.equal(cleaned.theme, 'dark');
  assert.equal(cleaned.hooks.SessionStart.length, 1);
  assert.equal(cleaned.hooks.SessionStart[0].hooks[0].name, 'other');
});
