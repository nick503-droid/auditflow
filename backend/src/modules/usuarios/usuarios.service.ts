import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Usuario } from './entities/usuario.entity';
import { CreateUsuarioDto } from './dto/create-usuario.dto';
import { UpdateUsuarioDto } from './dto/update-usuario.dto';
import * as bcrypt from 'bcryptjs';
import { pbkdf2Sync, randomBytes } from 'crypto';

const OFFLINE_ITERATIONS = 210_000;

@Injectable()
export class UsuariosService {
  constructor(
    @InjectRepository(Usuario)
    private usuariosRepo: Repository<Usuario>,
  ) {}

  findAll() {
    return this.usuariosRepo.find({
      where: { activo: 1 },
      // El catálogo de administración/PC nunca necesita el hash de contraseña.
      select: ['id', 'nombre', 'username', 'role', 'activo', 'require_password_change'],
    });
  }

  findOne(id: string) {
    return this.usuariosRepo.findOne({
      where: { id },
      select: ['id', 'nombre', 'username', 'role', 'activo', 'require_password_change'],
    });
  }

  findByUsername(username: string) {
    return this.usuariosRepo.findOne({ where: { username } });
  }

  async create(dto: CreateUsuarioDto) {
    const data: Partial<Usuario> = {
      nombre: dto.nombre,
      role: dto.role,
    };

    if (dto.username) {
      data.username = dto.username;
    }
    if (dto.password) {
      data.password = await bcrypt.hash(dto.password, 10);
      Object.assign(data, this.crearVerificadorOffline(dto.password));
    }

    const nuevo = this.usuariosRepo.create(data);
    const creado = await this.usuariosRepo.save(nuevo);
    return this.findOne(creado.id);
  }

  async update(id: string, dto: UpdateUsuarioDto) {
    const cambios: Partial<Usuario> = { ...dto };
    if (dto.password) {
      cambios.password = await bcrypt.hash(dto.password, 10);
      Object.assign(cambios, this.crearVerificadorOffline(dto.password));
    }
    await this.usuariosRepo.update(id, cambios);
    return this.findOne(id);
  }

  async changePassword(id: string, newPassword: string) {
    const hash = await bcrypt.hash(newPassword, 10);
    await this.usuariosRepo.update(id, {
      password: hash, 
      require_password_change: false,
      ...this.crearVerificadorOffline(newPassword),
    });
    return { success: true };
  }

  /** Inicializa cuentas antiguas cuando su titular logra autenticarse online. */
  async asegurarVerificadorOffline(usuario: Usuario, password: string): Promise<void> {
    if (usuario.offline_salt && usuario.offline_verifier) return;
    await this.usuariosRepo.update(usuario.id, this.crearVerificadorOffline(password));
  }

  async directorioOffline() {
    const usuarios = await this.usuariosRepo.find({
      where: { activo: 1 },
      select: [
        'id', 'nombre', 'username', 'role', 'require_password_change',
        'offline_salt', 'offline_verifier',
      ],
    });
    return usuarios
      .filter((u) => u.username && u.offline_salt && u.offline_verifier)
      .map((u) => ({
        id: u.id,
        nombre: u.nombre,
        username: u.username,
        role: u.role,
        require_password_change: u.require_password_change,
        salt: u.offline_salt,
        verifier: u.offline_verifier,
        iterations: OFFLINE_ITERATIONS,
      }));
  }

  private crearVerificadorOffline(password: string): Pick<Usuario, 'offline_salt' | 'offline_verifier'> {
    const salt = randomBytes(16);
    return {
      offline_salt: salt.toString('base64'),
      offline_verifier: pbkdf2Sync(password, salt, OFFLINE_ITERATIONS, 32, 'sha512').toString('base64'),
    };
  }

  remove(id: string) {
    return this.usuariosRepo.softDelete(id);
  }
}
