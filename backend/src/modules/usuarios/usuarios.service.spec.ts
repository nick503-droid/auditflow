import { UsuariosService } from './usuarios.service';
import { UsuariosController } from './usuarios.controller';
import { AuthService } from '../auth/auth.service';
import { RolUsuario } from './entities/usuario.entity';
import * as bcrypt from 'bcryptjs';
import { pbkdf2Sync } from 'crypto';

describe('Catálogo de usuarios y acceso temporal (sin DB/red)', () => {
  let rows: any[];
  let repo: any;
  let service: UsuariosService;
  let auth: AuthService;
  beforeEach(async () => {
    rows = [
      {
        id: 'a',
        nombre: 'Administrador',
        username: 'admin',
        role: RolUsuario.ADMIN,
        activo: 1,
        password: await bcrypt.hash('actual123', 4),
        require_password_change: false,
      },
      {
        id: 'e',
        nombre: 'Empleado',
        username: 'empleado',
        role: RolUsuario.EMPLEADO,
        activo: 1,
        password: await bcrypt.hash('anterior123', 4),
        require_password_change: false,
      },
    ];
    const matches = (row: any, where: any = {}) =>
      Object.entries(where).every(([k, v]) => row[k] === v);
    const project = (row: any, select?: string[]) =>
      row
        ? select
          ? Object.fromEntries(select.map((k) => [k, row[k]]))
          : { ...row }
        : null;
    repo = {
      find: jest.fn(async (o: any = {}) =>
        rows
          .filter((r) => matches(r, o.where))
          .map((r) => project(r, o.select)),
      ),
      findOne: jest.fn(async (o: any) =>
        project(
          rows.find((r) => matches(r, o.where)),
          o.select,
        ),
      ),
      update: jest.fn(async (id: string, dto: any) => {
        Object.assign(
          rows.find((r) => r.id === id),
          dto,
        );
        return { affected: 1 };
      }),
      create: jest.fn((dto) => dto),
      save: jest.fn(async (dto) => {
        const row = { id: 'nuevo', activo: 1, ...dto };
        rows.push(row);
        return row;
      }),
      softDelete: jest.fn(),
    };
    repo.manager = {
      transaction: jest.fn(async (fn) => fn({ getRepository: () => repo })),
    };
    service = new UsuariosService(repo);
    auth = new AuthService(service);
  });

  it('separa los catálogos activos y administrativos sin exponer hashes', async () => {
    rows[1].activo = 0;
    expect(await service.findAll()).toHaveLength(1);
    expect(await service.findAll(true)).toHaveLength(2);
    for (const row of await service.findAll(true)) {
      expect(row).not.toHaveProperty('password');
      expect(row).not.toHaveProperty('offline_verifier');
    }
  });

  it('edita nombre y usuario por ID sin cambiar contraseña ni crear otra cuenta', async () => {
    const hash = rows[1].password;
    const result = await service.update('e', {
      nombre: ' Walter ',
      username: ' walter ',
    });
    expect(result).toMatchObject({
      id: 'e',
      nombre: 'Walter',
      username: 'walter',
    });
    expect(rows[1].password).toBe(hash);
    expect(repo.save).not.toHaveBeenCalled();
  });

  it('desactiva y reactiva sin borrar, bloqueando el login mientras está inactivo', async () => {
    await service.remove('e');
    await expect(auth.login('empleado', 'anterior123')).rejects.toThrow();
    expect(repo.softDelete).not.toHaveBeenCalled();
    await service.update('e', { activo: 1 });
    expect(await auth.login('empleado', 'anterior123')).toMatchObject({
      id: 'e',
    });
    expect(rows).toHaveLength(2);
  });

  it.each([{ activo: 0 }, { role: RolUsuario.EMPLEADO }])(
    'protege al último administrador con bloqueo transaccional: %j',
    async (changes) => {
      await expect(service.update('a', changes)).rejects.toThrow(
        'último administrador',
      );
      expect(repo.find).toHaveBeenCalledWith({
        order: { id: 'ASC' },
        lock: { mode: 'pessimistic_write' },
      });
      expect(repo.update).not.toHaveBeenCalled();
    },
  );

  it('permite desactivar un administrador si otro activo con credenciales permanece', async () => {
    rows[1].role = RolUsuario.ADMIN;
    await expect(service.update('a', { activo: 0 })).resolves.toMatchObject({
      activo: 0,
    });
  });

  it('rechaza duplicados con mensaje útil también cuando la cuenta ya está inactiva', async () => {
    repo.update.mockRejectedValueOnce({
      driverError: { code: 'ER_DUP_ENTRY' },
    });
    await expect(service.update('e', { username: 'admin' })).rejects.toThrow(
      'ya existe',
    );
  });

  it('restablece a temporal, rechaza la anterior y exige otra contraseña distinta', async () => {
    const oldHash = rows[1].password;
    const result = await service.resetPassword('e', 'password123');
    expect(result).toMatchObject({ id: 'e', require_password_change: true });
    expect(result).not.toHaveProperty('password');
    expect(rows[1].password).not.toBe(oldHash);
    expect(await bcrypt.compare('password123', rows[1].password)).toBe(true);
    await expect(auth.login('empleado', 'anterior123')).rejects.toThrow();
    expect(await auth.login('empleado', 'password123')).toMatchObject({
      require_password_change: true,
    });
    await expect(service.changePassword('e', 'password123')).rejects.toThrow(
      'diferente',
    );
    await service.changePassword('e', 'definitiva456');
    expect(rows[1].require_password_change).toBe(false);
    await expect(auth.login('empleado', 'password123')).rejects.toThrow();
    expect(await auth.login('empleado', 'definitiva456')).toMatchObject({
      require_password_change: false,
    });
    const expected = pbkdf2Sync(
      'definitiva456',
      Buffer.from(rows[1].offline_salt, 'base64'),
      210000,
      32,
      'sha512',
    ).toString('base64');
    expect(rows[1].offline_verifier).toBe(expected);
  });

  it('actualizar password por el endpoint antiguo también obliga a cambiarla', async () => {
    await service.update('e', { password: 'temporal123' });
    expect(rows[1].require_password_change).toBe(true);
  });

  it('no permite cambiar contraseña definitiva en una cuenta inactiva', async () => {
    rows[1].activo = 0;
    await expect(service.changePassword('e', 'definitiva456')).rejects.toThrow(
      'Cuenta activa',
    );
  });

  it.each(['123', '      ', 'á'.repeat(40)])(
    'valida contraseña antes de modificar: %s',
    async (password) => {
      await expect(service.resetPassword('e', password)).rejects.toThrow(
        'contraseña',
      );
      expect(repo.update).not.toHaveBeenCalled();
    },
  );

  it('rechaza nombres, usuarios y estados inválidos', async () => {
    await expect(service.update('e', { nombre: '  ' })).rejects.toThrow();
    await expect(
      service.update('e', { username: 'con espacios' }),
    ).rejects.toThrow();
    await expect(service.update('e', { activo: 2 })).rejects.toThrow();
    await expect(
      service.update('missing', { nombre: 'Nombre' }),
    ).rejects.toThrow('no encontrado');
  });

  it('no recrea el seeder cuando hay cuentas inactivas o borradas antiguas', async () => {
    rows.forEach((r) => {
      r.activo = 0;
      r.deleted_at = new Date();
    });
    await auth.onModuleInit();
    expect(repo.find).toHaveBeenCalledWith({
      withDeleted: true,
      select: ['username'],
    });
    expect(repo.save).not.toHaveBeenCalled();
  });

  it('sigue creando el admin inicial sólo en una instalación sin cuentas', async () => {
    rows.length = 0;
    await auth.onModuleInit();
    expect(rows[0]).toMatchObject({
      username: 'admin',
      role: RolUsuario.ADMIN,
      require_password_change: true,
    });
  });

  it('el directorio offline excluye inactivos y actualiza los verificadores', async () => {
    await service.resetPassword('e', 'temporal123');
    expect(await service.directorioOffline()).toEqual([
      expect.objectContaining({ id: 'e', require_password_change: true }),
    ]);
    await service.update('e', { activo: 0 });
    expect(await service.directorioOffline()).toEqual([]);
  });

  it('el controlador separa administración, restablecimiento y cambio definitivo', async () => {
    const controller = new UsuariosController(service);
    expect(await controller.findAllAdmin()).toHaveLength(2);
    expect(
      await controller.resetPassword('e', { newPassword: 'temporal123' }),
    ).toMatchObject({ require_password_change: true });
    expect(
      await controller.changePassword('e', { newPassword: 'definitiva123' }),
    ).toEqual({ success: true });
  });
});
