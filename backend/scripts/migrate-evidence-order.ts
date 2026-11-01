/** Idempotente; sólo añade columnas e índices. No reconstruye fechas antiguas. */
import * as mysql from 'mysql2/promise';
import * as dotenv from 'dotenv';
import * as path from 'path';

export async function migrateEvidenceOrder(conn: mysql.Connection) {
  for (const [table, parent, index] of [
    ['evidencias_reporte', 'reporte_id', 'uq_ev_reporte_adicion'],
    ['evidencias_bitacora', 'bitacora_id', 'uq_ev_bitacora_adicion'],
  ]) {
    for (const [column, definition] of [
      ['agregado_en', 'DATETIME(3) NULL'],
      ['secuencia_adicion', 'BIGINT UNSIGNED NULL'],
    ]) {
      const [rows] = await conn.execute<mysql.RowDataPacket[]>(
        'SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND COLUMN_NAME=?',
        [table, column],
      );
      if (!rows.length) await conn.query(`ALTER TABLE \`${table}\` ADD COLUMN \`${column}\` ${definition}`);
    }
    const [indexes] = await conn.execute<mysql.RowDataPacket[]>(
      'SELECT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND INDEX_NAME=?',
      [table, index],
    );
    if (!indexes.length) await conn.query(`CREATE UNIQUE INDEX \`${index}\` ON \`${table}\` (\`${parent}\`, \`secuencia_adicion\`)`);
  }
}

async function main() {
  dotenv.config({ path: path.resolve(__dirname, '..', '.env') });
  const conn = await mysql.createConnection({
    host: process.env.DB_HOST ?? 'localhost', port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? process.env.DB_USERNAME ?? 'root',
    password: process.env.DB_PASS ?? process.env.DB_PASSWORD ?? '',
    database: process.env.DB_NAME ?? process.env.DB_DATABASE ?? 'auditflow',
  });
  try { await migrateEvidenceOrder(conn); } finally { await conn.end(); }
}
if (require.main === module) main().catch((error) => { console.error(error); process.exitCode = 1; });
