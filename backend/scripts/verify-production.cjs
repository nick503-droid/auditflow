// Smoke test del entrypoint REAL, sin conectarse a DB, escuchar puertos ni ejecutar seeds.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const command = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).scripts['start:prod'];
const match = /^node (dist\/[A-Za-z0-9_./-]+\.js)$/.exec(command);
assert.ok(match, 'start:prod debe señalar explícitamente un entrypoint .js dentro de dist/');
const entry = path.resolve(root, match[1]);
assert.ok(entry.startsWith(path.join(root, 'dist') + path.sep), 'Entrypoint fuera de dist/');
assert.ok(fs.statSync(entry).isFile(), `No existe el entrypoint de producción: ${entry}`);
if (process.env.AUDITFLOW_EXPECTED_COMMIT) {
  const metadata = JSON.parse(fs.readFileSync(path.join(root, 'deployment.json'), 'utf8'));
  assert.equal(metadata.commit, process.env.AUDITFLOW_EXPECTED_COMMIT, 'Identidad de imagen incorrecta');
}

const probe = `
  const assert = require('node:assert/strict');
  const { NestFactory } = require('@nestjs/core');
  let created = false, listening = false;
  NestFactory.create = async () => {
    created = true;
    return {
      use() {}, enableCors() {}, useGlobalPipes() {}, useGlobalFilters() {},
      async listen(port, host) {
        assert.equal(port, 3000); assert.equal(host, '0.0.0.0'); listening = true;
      }
    };
  };
  require(process.argv[1]);
  setImmediate(() => {
    assert.ok(created && listening, 'El entrypoint no ejecutó el bootstrap esperado');
    process.exit(0); // Dependencias importadas pueden mantener timers globales.
  });
`;
const result = spawnSync(process.execPath, ['-e', probe, entry], {
  cwd: root, env: { ...process.env, NODE_ENV: 'production' }, encoding: 'utf8', timeout: 20000,
});
assert.equal(result.status, 0, result.error?.message || result.stderr || 'Falló el bootstrap aislado');
console.log(`Entrypoint verificado sin DB/red: ${match[1]}`);
