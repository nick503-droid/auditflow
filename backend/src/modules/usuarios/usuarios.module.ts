import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Usuario } from './entities/usuario.entity';
import { UsuariosController } from './usuarios.controller';
import { UsuariosService } from './usuarios.service';

@Module({
  imports: [TypeOrmModule.forFeature([Usuario])], // registra la entity en este módulo
  controllers: [UsuariosController],
  providers: [UsuariosService],
  exports: [UsuariosService], // Permite que AuthModule lo consuma
})
export class UsuariosModule {}
