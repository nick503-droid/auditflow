/**
 * Schema para el orden estable de bitácoras. Idempotente; no borra registros.
 * DB_SYNC=true aplica lo mismo al arrancar. Para DB_SYNC=false, antes de
 * arrancar el backend nuevo: npm run migrate:bitacora-created-at
 *
 * Si no existía created_at, MySQL rellena las filas anteriores con el instante
 * de esta migración. Es una referencia estable, NO su creación histórica.
 * Los empates se resuelven por UUID, nunca por hora ni updated_at.
 */
import * as mysql from 'mysql2/promise';
import * as dotenv from 'dotenv';
import * as path from 'path';

export async function migrateBitacoraCreatedAt(conn: mysql.Connection) {
  const [columns] = await conn.execute<mysql.RowDataPacket[]>(
    `SELECT COLUMN_NAME FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bitacoras'
       AND COLUMN_NAME = 'created_at'`,
  );
  if (columns.length === 0) {
    await conn.query(
      'ALTER TABLE `bitacoras` ADD COLUMN `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)',
    );
    console.log('Added bitacoras.created_at; legacy timestamps are migration time.');
  }
  const [indexes] = await conn.execute<mysql.RowDataPacket[]>(
    `SELECT INDEX_NAME FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bitacoras'
       AND INDEX_NAME = 'idx_bitacoras_fecha_creacion'`,
  );
  if (indexes.length === 0) {
    await conn.query(
      'CREATE INDEX `idx_bitacoras_fecha_creacion` ON `bitacoras` (`fecha`, `created_at`, `id`)',
    );
    console.log('Added bitacora creation order index.');
  }
}

async function main() {
  dotenv.config({ path: path.resolve(__dirname, '..', '.env') });
  const conn = await mysql.createConnection({
    host: process.env.DB_HOST ?? 'localhost',
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? process.env.DB_USERNAME ?? 'root',
    password: process.env.DB_PASS ?? process.env.DB_PASSWORD ?? '',
    database: process.env.DB_NAME ?? process.env.DB_DATABASE ?? 'auditflow',
  });
  try {
    await migrateBitacoraCreatedAt(conn);
  } finally {
    await conn.end();
  }
}

if (require.main === module) {
  main().catch((error: unknown) => {
    console.error('Bitacora creation order migration failed:', error);
    process.exitCode = 1;
  });
}
