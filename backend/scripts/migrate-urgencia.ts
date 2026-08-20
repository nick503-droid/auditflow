/**
 * migrate-urgencia.ts
 *
 * Script de remapeo de datos: convierte los valores de urgencia del enum
 * antiguo (low / medium / critical) al nuevo (leve / medio / grave).
 * También amplía el enum en la tabla para incluir 'comentar'.
 *
 * INSTRUCCIONES DE USO (una sola vez, ANTES de desplegar el nuevo código):
 *   1. Asegúrate de que el .env esté disponible (mismo directorio que la app).
 *   2. Corre:  npm run migrate:urgencia
 *   3. Verifica la salida: debe mostrar 0 filas con valores viejos.
 *   4. Recién entonces despliega el nuevo código con el enum actualizado.
 *
 * El script es idempotente: si ya no hay valores viejos, el UPDATE
 * afecta 0 filas y el ALTER TABLE ya tiene el enum correcto (no-op en MySQL).
 */

import * as mysql from 'mysql2/promise';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Cargar .env desde la raíz del backend (un nivel arriba de /scripts)
dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

const cfg = {
  host:     process.env.DB_HOST     ?? 'localhost',
  port:     Number(process.env.DB_PORT ?? 3306),
  user:     process.env.DB_USERNAME ?? 'root',
  password: process.env.DB_PASSWORD ?? '',
  database: process.env.DB_DATABASE ?? 'auditflow',
  multipleStatements: false,
};

async function main() {
  console.log('=== migrate-urgencia =============================================');
  console.log(`Conectando a ${cfg.host}:${cfg.port}/${cfg.database} …`);

  const conn = await mysql.createConnection(cfg);

  try {
    // ── Paso A: remapear valores existentes ──────────────────────────────────
    console.log('\n[A] Remapeando valores de urgencia …');

    const [resultA] = await conn.execute<mysql.ResultSetHeader>(
      `UPDATE \`bitacoras\`
       SET \`urgencia\` = CASE \`urgencia\`
         WHEN 'low'      THEN 'leve'
         WHEN 'medium'   THEN 'medio'
         WHEN 'critical' THEN 'grave'
         ELSE \`urgencia\`
       END
       WHERE \`urgencia\` IN ('low', 'medium', 'critical')`,
    );
    console.log(`   ✅  Filas actualizadas: ${resultA.affectedRows}`);

    // ── Paso B: ampliar el enum ──────────────────────────────────────────────
    console.log('\n[B] Modificando columna urgencia al nuevo ENUM …');

    // Nota: ALTER TABLE en MySQL es DDL — no puede ir dentro de una
    // transacción en el mismo sentido que DML; lo ejecutamos directamente.
    await conn.query(
      `ALTER TABLE \`bitacoras\`
       MODIFY COLUMN \`urgencia\`
       ENUM('comentar', 'leve', 'medio', 'grave') NOT NULL DEFAULT 'leve'`,
    );
    console.log('   ✅  Columna modificada correctamente.');

    // ── Verificación final ───────────────────────────────────────────────────
    console.log('\n[V] Verificando valores distintos en la tabla …');
    const [rows] = await conn.execute<mysql.RowDataPacket[]>(
      `SELECT DISTINCT \`urgencia\` FROM \`bitacoras\` ORDER BY \`urgencia\``,
    );
    const valores = rows.map((r) => r['urgencia']);
    console.log(`   Valores encontrados: [${valores.join(', ')}]`);

    const valoresViejos = valores.filter((v) =>
      ['low', 'medium', 'critical'].includes(v),
    );
    if (valoresViejos.length > 0) {
      console.error(
        `\n❌  ERROR: todavía hay valores fuera del nuevo enum: [${valoresViejos.join(', ')}]`,
      );
      console.error('   NO despliegues el nuevo código hasta resolverlo.');
      process.exit(1);
    }

    console.log('\n✅  Migración completada. Puedes desplegar el nuevo código.');
    process.exit(0);
  } catch (err) {
    console.error('\n❌  Error durante la migración:', err);
    process.exit(1);
  } finally {
    await conn.end();
  }
}

main();
