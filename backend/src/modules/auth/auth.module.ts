import { Module } from '@nestjs/common';
import { AuthService } from './auth.service';
import { AuthController } from './auth.controller';
import { UsuariosModule } from '../usuarios/usuarios.module';

@Module({
  imports: [UsuariosModule], // Importa el módulo que exporta UsuariosService
  controllers: [AuthController],
  providers: [AuthService],
})
export class AuthModule {}
