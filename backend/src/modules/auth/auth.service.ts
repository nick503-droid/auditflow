import {
  Injectable,
  UnauthorizedException,
  OnModuleInit,
  Logger,
} from '@nestjs/common';
import { UsuariosService } from '../usuarios/usuarios.service';
import { RolUsuario } from '../usuarios/entities/usuario.entity';
import * as bcrypt from 'bcryptjs';

@Injectable()
export class AuthService implements OnModuleInit {
  private readonly logger = new Logger(AuthService.name);

  constructor(private readonly usuariosService: UsuariosService) {}

  /**
   * Seeder: Si no existe ningún usuario con credenciales al arrancar,
   * crea el superusuario admin / admin123 de forma automática.
   */
  async onModuleInit() {
    const todos = await this.usuariosService.findAll();
    const tieneAdmin = todos.some((u) => u.username !== null);

    if (!tieneAdmin) {
      await this.usuariosService.create({
        nombre: 'Administrador',
        username: 'admin',
        password: 'admin123',
        role: RolUsuario.ADMIN,
      });
      this.logger.log('✅ Seeder: Usuario admin por defecto creado (admin/admin123)');
    }
  }

  async login(username: string, password: string) {
    const usuario = await this.usuariosService.findByUsername(username);

    if (!usuario || !usuario.password) {
      throw new UnauthorizedException('Credenciales incorrectas');
    }

    const passwordValida = await bcrypt.compare(password, usuario.password);
    if (!passwordValida) {
      throw new UnauthorizedException('Credenciales incorrectas');
    }

    // Devolver perfil limpio, sin el hash de la contraseña
    return {
      id: usuario.id,
      nombre: usuario.nombre,
      username: usuario.username,
      role: usuario.role,
    };
  }
}
