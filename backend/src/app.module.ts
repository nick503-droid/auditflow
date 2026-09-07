import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { UsuariosModule } from './modules/usuarios/usuarios.module';
import { RestaurantesModule } from './modules/restaurantes/restaurantes.module';
import { BitacorasModule } from './modules/bitacoras/bitacoras.module';
import { ReportesModule } from './modules/reportes/reportes.module';
import { EvidenciasReporteModule } from './modules/evidencias-reporte/evidencias-reporte.module';
import { StorageModule } from './common/storage/storage.module';
import { UploadsModule } from './modules/uploads/uploads.module';
import { MobileSyncModule } from './modules/mobile-sync/mobile-sync.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      // En producción, Docker inyecta variables directamente al SO (process.env). 
      // Ignoramos la búsqueda del archivo .env que fue excluido por .dockerignore
      ignoreEnvFile: process.env.NODE_ENV === 'production',
      ignoreEnvVars: false,
    }),

    // Conexión a MySQL, usando las variables inyectadas
    TypeOrmModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        type: 'mysql',
        host: config.get('DB_HOST'),
        port: config.get('DB_PORT', 3306),
        // Mapea tanto los nombres viejos como los nuevos de producción
        username: config.get('DB_USER') || config.get('DB_USERNAME'),
        password: config.get('DB_PASS') || config.get('DB_PASSWORD'),
        database: config.get('DB_NAME') || config.get('DB_DATABASE'),
        autoLoadEntities: true,
        // En producción 'DB_SYNC' puede controlarse explícitamente, o false por defecto
        synchronize: config.get('DB_SYNC') === 'true' || config.get('NODE_ENV') !== 'production',
        logging: config.get('NODE_ENV') === 'development' ? ['error', 'warn'] : false,
      }),
    }),

    UsuariosModule,

    RestaurantesModule,

    BitacorasModule,

    ReportesModule,

    EvidenciasReporteModule,

    StorageModule,

    UploadsModule,
    
    MobileSyncModule,
  ],
})
export class AppModule {}