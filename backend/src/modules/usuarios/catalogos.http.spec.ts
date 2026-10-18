import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import request from 'supertest';
import { UsuariosController } from './usuarios.controller';
import { UsuariosService } from './usuarios.service';
import { RestaurantesController } from '../restaurantes/restaurantes.controller';
import { RestaurantesService } from '../restaurantes/restaurantes.service';

describe('Rutas y DTO de catálogos (aplicación aislada, sin DB)', () => {
  let app: INestApplication;
  const users = {
    findAll: jest.fn(() => []),
    findOne: jest.fn(() => ({ id: 'u' })),
    update: jest.fn(() => ({ id: 'u' })),
    resetPassword: jest.fn(() => ({ id: 'u', require_password_change: true })),
    changePassword: jest.fn(() => ({ success: true })),
  };
  const stores = {
    findAll: jest.fn(() => []),
    findOne: jest.fn(() => ({ id: 'r' })),
    update: jest.fn(() => ({ id: 'r' })),
  };
  beforeAll(async () => {
    const module = await Test.createTestingModule({
      controllers: [UsuariosController, RestaurantesController],
      providers: [
        { provide: UsuariosService, useValue: users },
        { provide: RestaurantesService, useValue: stores },
      ],
    }).compile();
    app = module.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({ whitelist: true }));
    await app.init();
  });
  beforeEach(() => jest.clearAllMocks());
  afterAll(async () => {
    await app.close();
  });

  it('admin no se interpreta como un ID de usuario', async () => {
    await request(app.getHttpServer()).get('/usuarios/admin').expect(200, []);
    expect(users.findAll).toHaveBeenCalledWith(true);
    expect(users.findOne).not.toHaveBeenCalled();
  });
  it('admin no se interpreta como un ID de restaurante', async () => {
    await request(app.getHttpServer())
      .get('/restaurantes/admin')
      .expect(200, []);
    expect(stores.findAll).toHaveBeenCalledWith(true);
  });
  it('mantiene el catálogo habitual separado del administrativo', async () => {
    await request(app.getHttpServer()).get('/usuarios').expect(200);
    expect(users.findAll).toHaveBeenCalledWith();
  });
  it('acepta estado numérico y elimina campos que no están permitidos', async () => {
    await request(app.getHttpServer())
      .patch('/usuarios/u')
      .send({ activo: 0, require_password_change: false })
      .expect(200);
    expect(users.update).toHaveBeenCalledWith('u', { activo: 0 });
  });
  it.each(['/usuarios/u', '/restaurantes/r'])(
    'rechaza estados no válidos en %s',
    async (url) => {
      await request(app.getHttpServer())
        .patch(url)
        .send({ activo: 3 })
        .expect(400);
    },
  );
  it('valida contraseña antes de restablecer', async () => {
    await request(app.getHttpServer())
      .patch('/usuarios/u/reset-password')
      .send({ newPassword: '123' })
      .expect(400);
    expect(users.resetPassword).not.toHaveBeenCalled();
    await request(app.getHttpServer())
      .patch('/usuarios/u/reset-password')
      .send({ newPassword: 'temporal123' })
      .expect(200);
    expect(users.resetPassword).toHaveBeenCalledWith('u', 'temporal123');
  });
  it('el cambio definitivo sigue siendo una operación distinta', async () => {
    await request(app.getHttpServer())
      .patch('/usuarios/u/password')
      .send({ newPassword: 'definitiva123' })
      .expect(200, { success: true });
    expect(users.changePassword).toHaveBeenCalledWith('u', 'definitiva123');
    expect(users.resetPassword).not.toHaveBeenCalled();
  });
});
