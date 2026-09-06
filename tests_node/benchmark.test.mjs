import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';

import {
  buildBenchmarkArgs,
  resolveBenchmarkConfig,
} from '../bin/lib/benchmark.mjs';

test('full benchmark defaults to practical 1k through 100k tiers', () => {
  const config = resolveBenchmarkConfig({}, '/tmp/work');
  assert.equal(config.sizes, '1000,10000,50000,100000');
  assert.equal(config.warmup, 5);
  assert.equal(config.iterations, 30);
  assert.equal(config.subprocessIterations, 10);
  assert.equal(config.output, path.resolve('/tmp/work', 'memcarry-benchmark.json'));
});

test('quick benchmark stays useful while reducing local repetitions', () => {
  const config = resolveBenchmarkConfig({ quick: true }, '/tmp/work');
  assert.equal(config.sizes, '1000,10000');
  assert.equal(config.warmup, 1);
  assert.equal(config.iterations, 5);
  assert.equal(config.subprocessIterations, 3);
});

test('explicit benchmark options override quick defaults', () => {
  const config = resolveBenchmarkConfig(
    {
      quick: true,
      sizes: '50',
      warmup: 0,
      iterations: 2,
      subprocessIterations: 1,
      output: 'result.json',
    },
    '/tmp/work',
  );
  assert.deepEqual(buildBenchmarkArgs('/pkg', config), [
    path.join('/pkg', 'benchmarks', 'machine_benchmark.py'),
    '--sizes', '50',
    '--warmup', '0',
    '--iterations', '2',
    '--subprocess-iterations', '1',
    '--output', path.resolve('/tmp/work', 'result.json'),
  ]);
});
