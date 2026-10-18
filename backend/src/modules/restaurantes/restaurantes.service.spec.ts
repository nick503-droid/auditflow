import { RestaurantesService } from './restaurantes.service';
import { RestaurantesController } from './restaurantes.controller';
import { migrateRestauranteActivo } from '../../../scripts/migrate-restaurante-activo';

describe('Catálogo de restaurantes (sin DB/red)', () => {
  let repo: any;
  let service: RestaurantesService;
  beforeEach(() => {
    repo = {
      find: jest.fn().mockResolvedValue([]),
      findOneBy: jest
        .fn()
        .mockResolvedValue({ id: 'r', nombre: 'Norco', activo: 1 }),
      update: jest.fn(),
      softDelete: jest.fn(),
      create: jest.fn((x) => x),
      save: jest.fn(async (x) => x),
    };
    service = new RestaurantesService(repo);
  });
  it('los selects de trabajo sólo incluyen activos y administración incluye ambos', async () => {
    await service.findAll();
    await new RestaurantesController(service).findAllAdmin();
    expect(repo.find.mock.calls[0][0].where).toEqual({ activo: 1 });
    expect(repo.find.mock.calls[1][0].where).toEqual({});
  });
  it('renombra por ID sin crear ni mover evidencias', async () => {
    await service.update('r', { nombre: ' Norco Norte ' });
    expect(repo.update).toHaveBeenCalledWith('r', { nombre: 'Norco Norte' });
    expect(repo.save).not.toHaveBeenCalled();
  });
  it('DELETE compatible desactiva y PATCH reactiva sin borrado físico/lógico', async () => {
    await service.remove('r');
    await service.update('r', { activo: 1 });
    expect(repo.update.mock.calls.map((x) => x[1])).toEqual([
      { activo: 0 },
      { activo: 1 },
    ]);
    expect(repo.softDelete).not.toHaveBeenCalled();
  });
  it('valida nombres y estados', async () => {
    expect(() => service.create({ nombre: ' ' })).toThrow();
    await expect(service.update('r', { activo: 3 })).rejects.toThrow();
    repo.findOneBy.mockResolvedValueOnce(null);
    await expect(
      service.update('missing', { nombre: 'Nombre' }),
    ).rejects.toThrow('no encontrado');
  });
  it('la migración agrega activo=1 una sola vez sin borrar datos', async () => {
    const conn = {
      execute: jest
        .fn()
        .mockResolvedValueOnce([[]])
        .mockResolvedValueOnce([[{ COLUMN_NAME: 'activo' }]]),
      query: jest.fn(),
    };
    await migrateRestauranteActivo(conn as any);
    await migrateRestauranteActivo(conn as any);
    expect(conn.query).toHaveBeenCalledTimes(1);
    expect(conn.query).toHaveBeenCalledWith(
      'ALTER TABLE `restaurantes` ADD COLUMN `activo` TINYINT NOT NULL DEFAULT 1',
    );
  });
});
