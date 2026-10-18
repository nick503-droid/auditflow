import {
  BadRequestException,
  ConflictException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Usuario, RolUsuario } from './entities/usuario.entity';
import { CreateUsuarioDto } from './dto/create-usuario.dto';
import { UpdateUsuarioDto } from './dto/update-usuario.dto';
import * as bcrypt from 'bcryptjs';
import { pbkdf2Sync, randomBytes } from 'crypto';

const OFFLINE_ITERATIONS = 210_000;
const PUBLIC_FIELDS: (keyof Usuario)[] = [
  'id',
  'nombre',
  'username',
  'role',
  'activo',
  'require_password_change',
];

@Injectable()
export class UsuariosService {
  constructor(
    @InjectRepository(Usuario)
    private usuariosRepo: Repository<Usuario>,
  ) {}

  findAll(incluirInactivos = false) {
    return this.usuariosRepo.find({
      where: incluirInactivos ? {} : { activo: 1 },
      // El catálogo de administración/PC nunca necesita el hash de contraseña.
      select: PUBLIC_FIELDS,
      order: { nombre: 'ASC', id: 'ASC' },
    });
  }

  findOne(id: string) {
    return this.usuariosRepo.findOne({
      where: { id },
      select: PUBLIC_FIELDS,
    });
  }

  findByUsername(username: string) {
    return this.usuariosRepo.findOne({
      where: { username: username.trim(), activo: 1 },
    });
  }

  async tieneCuentasRegistradas() {
    // Incluye inactivos y borrados antiguos: no recrear admin/admin123 al desactivar.
    const cuentas = await this.usuariosRepo.find({
      withDeleted: true,
      select: ['username'],
    });
    return cuentas.some((u) => Boolean(u.username));
  }

  private nombreValido(value: string) {
    if (
      typeof value !== 'string' ||
      !value.trim() ||
      value.trim().length > 255
    ) {
      throw new BadRequestException(
        'El nombre es obligatorio y admite hasta 255 caracteres.',
      );
    }
    return value.trim();
  }

  private usernameValido(value: string) {
    if (
      typeof value !== 'string' ||
      !value.trim() ||
      /\s/.test(value.trim()) ||
      value.trim().length > 255
    ) {
      throw new BadRequestException(
        'El usuario es obligatorio y no debe contener espacios.',
      );
    }
    return value.trim();
  }

  private validarPassword(password: string) {
    if (
      typeof password !== 'string' ||
      password.trim().length < 6 ||
      Buffer.byteLength(password, 'utf8') > 72
    ) {
      throw new BadRequestException(
        'La contraseña debe tener al menos 6 caracteres y no superar 72 bytes.',
      );
    }
  }

  private async guardarSinDuplicado<T>(
    operacion: () => Promise<T>,
  ): Promise<T> {
    try {
      return await operacion();
    } catch (error) {
      if ((error?.driverError?.code ?? error?.code) === 'ER_DUP_ENTRY') {
        throw new ConflictException(
          'Ese usuario de inicio de sesión ya existe, incluso si está inactivo.',
        );
      }
      throw error;
    }
  }

  async create(dto: CreateUsuarioDto) {
    const data: Partial<Usuario> = {
      nombre: this.nombreValido(dto.nombre),
      role: dto.role,
    };

    if (dto.username !== undefined) {
      data.username = this.usernameValido(dto.username);
    }
    if (dto.password !== undefined) {
      this.validarPassword(dto.password);
      if (!data.username)
        throw new BadRequestException(
          'Se necesita un usuario para asignar contraseña.',
        );
      data.password = await bcrypt.hash(dto.password, 10);
      data.require_password_change = true;
      Object.assign(data, this.crearVerificadorOffline(dto.password));
    }

    const nuevo = this.usuariosRepo.create(data);
    const creado = await this.guardarSinDuplicado(() =>
      this.usuariosRepo.save(nuevo),
    );
    return this.findOne(creado.id);
  }

  async update(id: string, dto: UpdateUsuarioDto) {
    const cambios: Partial<Usuario> = {};
    if (dto.nombre !== undefined)
      cambios.nombre = this.nombreValido(dto.nombre);
    if (dto.username !== undefined)
      cambios.username = this.usernameValido(dto.username);
    if (dto.role !== undefined) {
      if (!Object.values(RolUsuario).includes(dto.role))
        throw new BadRequestException('Rol no válido.');
      cambios.role = dto.role;
    }
    if (dto.activo !== undefined) {
      if (dto.activo !== 0 && dto.activo !== 1)
        throw new BadRequestException('Estado no válido.');
      cambios.activo = dto.activo;
    }
    if (dto.password !== undefined) {
      this.validarPassword(dto.password);
      cambios.password = await bcrypt.hash(dto.password, 10);
      cambios.require_password_change = true;
      Object.assign(cambios, this.crearVerificadorOffline(dto.password));
    }
    return this.guardarSinDuplicado(() =>
      this.usuariosRepo.manager.transaction(async (manager) => {
        const repo = manager.getRepository(Usuario);
        // Orden y bloqueo común: dos administradores no pueden desactivar al último a la vez.
        const usuarios = await repo.find({
          order: { id: 'ASC' },
          lock: { mode: 'pessimistic_write' },
        });
        const actual = usuarios.find((u) => u.id === id);
        if (!actual) throw new NotFoundException('Usuario no encontrado.');
        const siguiente = { ...actual, ...cambios };
        if (
          siguiente.role === RolUsuario.ADMIN &&
          siguiente.activo === 1 &&
          (!siguiente.username || !siguiente.password)
        ) {
          throw new BadRequestException(
            'Un administrador activo necesita usuario y contraseña.',
          );
        }
        if (
          actual.role === RolUsuario.ADMIN &&
          actual.activo === 1 &&
          (siguiente.role !== RolUsuario.ADMIN || siguiente.activo !== 1) &&
          !usuarios.some(
            (u) =>
              u.id !== id &&
              u.role === RolUsuario.ADMIN &&
              u.activo === 1 &&
              u.username &&
              u.password,
          )
        ) {
          throw new ConflictException(
            'No puedes desactivar ni cambiar el rol del último administrador activo.',
          );
        }
        if (Object.keys(cambios).length) await repo.update(id, cambios);
        return repo.findOne({ where: { id }, select: PUBLIC_FIELDS });
      }),
    );
  }

  async changePassword(id: string, newPassword: string) {
    this.validarPassword(newPassword);
    await this.usuariosRepo.manager.transaction(async (manager) => {
      const repo = manager.getRepository(Usuario);
      const usuario = await repo.findOne({
        where: { id, activo: 1 },
        lock: { mode: 'pessimistic_write' },
      });
      if (!usuario) throw new NotFoundException('Cuenta activa no encontrada.');
      if (
        usuario.require_password_change &&
        (await bcrypt.compare(newPassword, usuario.password || ''))
      ) {
        throw new BadRequestException(
          'La contraseña nueva debe ser diferente de la temporal.',
        );
      }
      const hash = await bcrypt.hash(newPassword, 10);
      await repo.update(id, {
        password: hash,
        require_password_change: false,
        ...this.crearVerificadorOffline(newPassword),
      });
    });
    return { success: true };
  }

  async resetPassword(id: string, temporaryPassword: string) {
    // No es el cambio definitivo: obliga a elegir otra contraseña al iniciar sesión.
    const usuario = await this.findOne(id);
    if (!usuario) throw new NotFoundException('Usuario no encontrado.');
    if (!usuario.username)
      throw new BadRequestException(
        'Asigna primero un usuario de inicio de sesión.',
      );
    return this.update(id, { password: temporaryPassword });
  }

  /** Inicializa cuentas antiguas cuando su titular logra autenticarse online. */
  async asegurarVerificadorOffline(
    usuario: Usuario,
    password: string,
  ): Promise<void> {
    if (usuario.offline_salt && usuario.offline_verifier) return;
    await this.usuariosRepo.update(
      usuario.id,
      this.crearVerificadorOffline(password),
    );
  }

  async directorioOffline() {
    const usuarios = await this.usuariosRepo.find({
      where: { activo: 1 },
      select: [
        'id',
        'nombre',
        'username',
        'role',
        'require_password_change',
        'offline_salt',
        'offline_verifier',
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

  private crearVerificadorOffline(
    password: string,
  ): Pick<Usuario, 'offline_salt' | 'offline_verifier'> {
    const salt = randomBytes(16);
    return {
      offline_salt: salt.toString('base64'),
      offline_verifier: pbkdf2Sync(
        password,
        salt,
        OFFLINE_ITERATIONS,
        32,
        'sha512',
      ).toString('base64'),
    };
  }

  remove(id: string) {
    // Compatibilidad con clientes antiguos: DELETE ahora desactiva, no borra historial.
    return this.update(id, { activo: 0 });
  }
}
