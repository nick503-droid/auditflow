/**
 * Adds the persistent idempotency key used by PC/offline bitacora retries.
 * Safe to run repeatedly. When DB_SYNC=true TypeORM can apply the same schema
 * change automatically; this script is for installations with synchronization
 * disabled.
 *
 * Run from backend/: npm run migrate:bitacora-client-id
 */

import * as mysql from 'mysql2/promise';
import * as dotenv from 'dotenv';
import * as path from 'path';

dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

const cfg = {
  host: process.env.DB_HOST ?? 'localhost',
  port: Number(process.env.DB_PORT ?? 3306),
  user: process.env.DB_USER ?? process.env.DB_USERNAME ?? 'root',
  password: process.env.DB_PASS ?? process.env.DB_PASSWORD ?? '',
  database: process.env.DB_NAME ?? process.env.DB_DATABASE ?? 'auditflow',
};

async function main() {
  const conn = await mysql.createConnection(cfg);
  try {
    const [columns] = await conn.execute<mysql.RowDataPacket[]>(
      `SELECT COLUMN_NAME FROM information_schema.COLUMNS
       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bitacoras'
         AND COLUMN_NAME = 'client_id'`,
    );
    if (columns.length === 0) {
      await conn.query(
        "ALTER TABLE `bitacoras` ADD COLUMN `client_id` VARCHAR(36) NULL",
      );
      console.log('Added bitacoras.client_id.');
    }

    const [indexes] = await conn.execute<mysql.RowDataPacket[]>(
      `SELECT INDEX_NAME FROM information_schema.STATISTICS
       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bitacoras'
         AND INDEX_NAME = 'uq_bitacoras_client_id'`,
    );
    if (indexes.length === 0) {
      await conn.query(
        'CREATE UNIQUE INDEX `uq_bitacoras_client_id` ON `bitacoras` (`client_id`)',
      );
      console.log('Added unique idempotency index.');
    }

    console.log('Bitacora client ID migration complete.');
  } finally {
    await conn.end();
  }
}

main().catch((error: unknown) => {
  console.error('Bitacora client ID migration failed:', error);
  process.exitCode = 1;
});
