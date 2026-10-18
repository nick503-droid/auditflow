/** No elimina filas. DB_SYNC=true crea también esta columna al arrancar. */
import * as mysql from 'mysql2/promise';
import * as dotenv from 'dotenv';
import * as path from 'path';

export async function migrateRestauranteActivo(conn: mysql.Connection) {
  const [columns] = await conn.execute<mysql.RowDataPacket[]>(
    `SELECT COLUMN_NAME FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'restaurantes' AND COLUMN_NAME = 'activo'`,
  );
  if (!columns.length) {
    await conn.query(
      'ALTER TABLE `restaurantes` ADD COLUMN `activo` TINYINT NOT NULL DEFAULT 1',
    );
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
    await migrateRestauranteActivo(conn);
  } finally {
    await conn.end();
  }
}
if (require.main === module)
  main().catch((error: unknown) => {
    console.error(error);
    process.exitCode = 1;
  });
