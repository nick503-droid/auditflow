import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Bitacora } from './entities/bitacora.entity';
import { BitacorasService } from './bitacoras.service';
import { BitacorasController } from './bitacoras.controller';

@Module({
  imports: [TypeOrmModule.forFeature([Bitacora])],
  controllers: [BitacorasController],
  providers: [BitacorasService],
})
export class BitacorasModule {}