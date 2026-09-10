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
import { SystemModule } from './modules/system/system.module';
import { AuthModule } from './modules/auth/auth.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      ignoreEnvFile: process.env.NODE_ENV === 'production',
      ignoreEnvVars: false,
    }),

    TypeOrmModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        type: 'mysql',
        host: config.get('DB_HOST'),
        port: config.get('DB_PORT', 3306),
        username: config.get('DB_USER') || config.get('DB_USERNAME'),
        password: config.get('DB_PASS') || config.get('DB_PASSWORD'),
        database: config.get('DB_NAME') || config.get('DB_DATABASE'),
        autoLoadEntities: true,
        synchronize: config.get('DB_SYNC') === 'true' || config.get('NODE_ENV') !== 'production',
        logging: config.get('NODE_ENV') === 'development' ? ['error', 'warn'] : false,
        extra: {
          connectionLimit: 50,
        },
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
    SystemModule,
    AuthModule,
  ],
})
export class AppModule {}