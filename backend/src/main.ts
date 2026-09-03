// main.ts
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';
import * as express from 'express';
import * as path from 'path';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors(); // Habilitar CORS para permitir peticiones desde Vue/Vite (Navegador)
  app.useGlobalPipes(new ValidationPipe({ whitelist: true }));
  
  // Exponer archivos estáticos
  const storagePath = process.env.STORAGE_PATH || path.resolve('./local_storage');
  app.use('/evidencias', express.static(storagePath));

  await app.listen(3000, '0.0.0.0');
}
bootstrap();