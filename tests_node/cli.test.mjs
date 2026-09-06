import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const BIN = path.join(ROOT, 'bin', 'agent-memory-hub.mjs');

function run(args) {
  return spawnSync(process.execPath, [BIN, ...args], { encoding: 'utf8' });
}

test('install status uninstall is idempotent and preserves unrelated settings/data', () => {
  const td = fs.mkdtempSync(path.join(os.tmpdir(), 'amh-cli-'));
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
  assert.equal(claude.hooks.SessionStart.filter(g => g.hooks?.some(h => h.name === 'agent-memory-hub')).length, 1);
  assert.equal(claude.hooks.SessionStart.filter(g => g.hooks?.some(h => h.name === 'other')).length, 1);
  assert.ok(fs.existsSync(`${claudeSettings}.agent-memory-hub.bak`));
  assert.ok(fs.existsSync(path.join(memoryHome, 'runtime', 'scripts', 'session_start_hook.py')));
  assert.ok(fs.existsSync(path.join(memoryHome, 'memory.db')));

  result = run(['status', '--home', memoryHome, '--user-home', userHome, '--agents', 'all']);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /runtime: installed/);
  assert.match(result.stdout, /codex: hooked/);
  assert.match(result.stdout, /claude: hooked/);
  assert.match(result.stdout, /gemini: hooked/);

  fs.writeFileSync(path.join(memoryHome, 'sentinel.txt'), 'keep');
  result = run(['uninstall', '--home', memoryHome, '--user-home', userHome, '--agents', 'all']);
  assert.equal(result.status, 0, result.stderr);
  assert.ok(!fs.existsSync(path.join(memoryHome, 'runtime')));
  assert.equal(fs.readFileSync(path.join(memoryHome, 'sentinel.txt'), 'utf8'), 'keep');
  assert.ok(fs.existsSync(path.join(memoryHome, 'memory.db')));

  const cleaned = JSON.parse(fs.readFileSync(claudeSettings, 'utf8'));
  assert.equal(cleaned.theme, 'dark');
  assert.equal(cleaned.hooks.SessionStart.length, 1);
  assert.equal(cleaned.hooks.SessionStart[0].hooks[0].name, 'other');
});
