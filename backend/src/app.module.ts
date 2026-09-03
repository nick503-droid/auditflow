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
    // Carga el .env y lo hace disponible en toda la app (como una store global)
    ConfigModule.forRoot({
      isGlobal: true,
    }),

    // Conexión a MySQL, usando las variables del .env
    TypeOrmModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        type: 'mysql',
        host: config.get('DB_HOST'),
        port: config.get('DB_PORT'),
        username: config.get('DB_USERNAME'),
        password: config.get('DB_PASSWORD'),
        database: config.get('DB_DATABASE'),
        autoLoadEntities: true, // detecta entities de cada módulo automáticamente
        synchronize: true, // ⚠️ solo en desarrollo: crea tablas automáticamente
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