// main.ts
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';
import * as express from 'express';
import * as path from 'path';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // ── PUERTA DE SALIDA (LOGGER DE PETICIONES) ───────────────────────────────
  // Esto imprimirá CADA petición que llegue al servidor antes de hacer nada.
  app.use((req: express.Request, res: express.Response, next: express.NextFunction) => {
    console.log(`[REQUEST] ${req.method} ${req.url} | Origen: ${req.headers.origin || 'N/A'}`);
    next();
  });

  // ── CORS ──────────────────────────────────────────────────────────────────
  // Lee orígenes permitidos desde la variable CORS_ORIGIN (lista separada por
  // comas). Si no está definida, usa una lista segura por defecto que cubre:
  //   • Vite dev server          (localhost:5173)
  //   • Backend propio           (localhost:3000)  — útil para health-checks
  //   • App Capacitor / Android  (capacitor://localhost)
  //   • Red local entera LAN     (cualquier 192.168.x.x)
  //
  // ⚠️  En producción define CORS_ORIGIN en el .env con los dominios reales.
  const rawOrigins = process.env.CORS_ORIGIN;
  const allowedOrigins: (string | RegExp)[] = rawOrigins
    ? rawOrigins.split(',').map((o) => o.trim())
    : [
        'http://localhost',
        'http://localhost:5173',
        'http://localhost:3000',
        'capacitor://localhost',
      ];

  // Añadir siempre los rangos de redes privadas (RFC 1918)
  // 192.168.x.x, 10.x.x.x, 172.16.x.x - 172.31.x.x
  allowedOrigins.push(/^https?:\/\/(192\.168|10|172\.(1[6-9]|2[0-9]|3[0-1]))\.\d{1,3}\.\d{1,3}(:\d+)?$/);

  app.enableCors({
    origin: (origin, callback) => {
      // Permitir peticiones sin origen (Postman, curl, CustomTkinter/requests)
      // y peticiones cuyo origen esté en la lista blanca.
      if (!origin) {
        return callback(null, true);
      }
      const permitido = allowedOrigins.some((o) =>
        o instanceof RegExp ? o.test(origin) : o === origin,
      );
      if (permitido) {
        callback(null, true);
      } else {
        callback(new Error(`Origen no permitido por CORS: ${origin}`));
      }
    },
    methods: ['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
    credentials: false,
  });

  // ── Validación Global ──────────────────────────────────────────────────────
  app.useGlobalPipes(new ValidationPipe({ whitelist: true }));

  // ── Filtros Globales ───────────────────────────────────────────────────────
  const { OptimisticLockFilter } = await import('./common/filters/optimistic-lock.filter');
  app.useGlobalFilters(new OptimisticLockFilter());

  // ── Archivos Estáticos ─────────────────────────────────────────────────────
  // STORAGE_PATH puede venir con comillas dobles en Windows (.env sin parser).
  // Las eliminamos para que path.resolve funcione correctamente.
  const storagePath = (process.env.STORAGE_PATH || './local_storage').replace(
    /^"|"$/g,
    '',
  );
  app.use('/evidencias', express.static(path.resolve(storagePath)));

  await app.listen(3000, '0.0.0.0');
  console.log(
    `[AuditFlow] Servidor listo en http://0.0.0.0:3000 (entorno: ${process.env.NODE_ENV ?? 'development'})`,
  );
}
bootstrap();