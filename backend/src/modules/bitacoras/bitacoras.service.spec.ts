import { BitacorasService } from './bitacoras.service';
import { Bitacora } from './entities/bitacora.entity';
import { DataSource, getMetadataArgsStorage, MoreThan } from 'typeorm';
import { EvidenciaBitacora } from './entities/evidencia-bitacora.entity';
import { Usuario } from '../usuarios/entities/usuario.entity';
import { Restaurante } from '../restaurantes/entities/restaurante.entity';
import { migrateBitacoraCreatedAt } from '../../../scripts/migrate-bitacora-created-at';

describe('BitacorasService', () => {
  let service: BitacorasService;
  let bitacorasRepo: {
    find: jest.Mock;
    findOne: jest.Mock;
    create: jest.Mock;
    save: jest.Mock;
  };

  beforeEach(() => {
    bitacorasRepo = {
      find: jest.fn(),
      findOne: jest.fn(),
      create: jest.fn((datos) => datos),
      save: jest.fn(),
    };
    service = new BitacorasService(
      bitacorasRepo as any,
      {} as any,
      {} as any,
      {} as any,
    );
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('orders day and delta queries by immutable server creation time with a stable tie break', () => {
    const desde = new Date('2026-10-17T20:00:00Z');
    service.findPorFecha('2026-10-17');
    service.findDesde('2026-10-17', desde);
    service.findAll();
    expect(bitacorasRepo.find.mock.calls[0][0]).toMatchObject({
      where: { fecha: '2026-10-17' }, order: { created_at: 'ASC', id: 'ASC' },
    });
    expect(bitacorasRepo.find.mock.calls[1][0]).toMatchObject({
      withDeleted: true, where: { updated_at: MoreThan(desde) },
      order: { created_at: 'ASC', id: 'ASC' },
    });
    expect(bitacorasRepo.find.mock.calls[2][0].order).toEqual({ fecha: 'DESC', created_at: 'ASC', id: 'ASC' });
    for (const [options] of bitacorasRepo.find.mock.calls) {
      expect(options.order).not.toHaveProperty('hora');
    }
  });

  it('lets MySQL generate created_at rather than accepting a PC timestamp', async () => {
    bitacorasRepo.findOne.mockResolvedValue(null);
    bitacorasRepo.save.mockImplementation(async (data) => data);
    await service.create({
      restaurante_id: 'restaurante-1', usuario_id: 'usuario-1',
      descripcion: 'Descripción multilínea\nSin recortar.', hora: '8:55 AM',
      evidencia_url: '/evidencias/legacy.mp4', con_audio: true,
      created_at: '1999-01-01T00:00:00Z', updated_at: '2099-01-01T00:00:00Z',
    } as any);
    const inserted = bitacorasRepo.create.mock.calls[0][0];
    expect(inserted).not.toHaveProperty('created_at');
    expect(inserted).not.toHaveProperty('updated_at');
    expect(inserted.descripcion).toBe('Descripción multilínea\nSin recortar.');
    expect(inserted.evidencia_url).toBe('/evidencias/legacy.mp4');
    expect(inserted.con_audio).toBe(true);
    const column = getMetadataArgsStorage().columns.find(c => c.target === Bitacora && c.propertyName === 'created_at');
    expect(column).toMatchObject({ mode: 'createDate', options: { precision: 3, update: false } });
  });

  it('builds compatible MySQL defaults and keeps creation time out of updates (without connecting)', async () => {
    class MetadataOnlySource extends DataSource {
      async loadMetadata() { await this.buildMetadatas(); }
    }
    const source = new MetadataOnlySource({
      type: 'mysql', database: 'fixture',
      entities: [Bitacora, EvidenciaBitacora, Usuario, Restaurante],
    });
    await source.loadMetadata();
    const column = source.getMetadata(Bitacora).columns.find(c => c.propertyName === 'created_at')!;
    expect(column.precision).toBe(3);
    expect(source.driver.normalizeDefault(column)).toBe('CURRENT_TIMESTAMP(3)');
    const sql = source.createQueryBuilder().update(Bitacora)
      .set({ hora: '8:55 AM', created_at: new Date('1999-01-01T00:00:00Z') })
      .where('id = :id', { id: 'fixture' }).getSql();
    expect(sql).not.toContain('created_at');
    expect(sql).toContain('updated_at');
  });

  it('returns the existing record when a client retries the same client_id', async () => {
    const existente = { id: 'bitacora-1', codigo: 'ABC123' };
    bitacorasRepo.findOne.mockResolvedValueOnce(existente);

    await expect(
      service.create({
        client_id: 'cfa63b35-4379-423a-b99f-2fa88019b21f',
        restaurante_id: 'restaurante-1',
        usuario_id: 'usuario-1',
      }),
    ).resolves.toBe(existente);

    expect(bitacorasRepo.create).not.toHaveBeenCalled();
    expect(bitacorasRepo.save).not.toHaveBeenCalled();
  });

  it('returns the winning record when two first attempts race on the unique key', async () => {
    const existente = { id: 'bitacora-1', codigo: 'ABC123' };
    bitacorasRepo.findOne
      .mockResolvedValueOnce(null) // lookup by client_id
      .mockResolvedValueOnce(null) // code collision check
      .mockResolvedValueOnce(existente); // lookup after unique-key conflict
    bitacorasRepo.save.mockRejectedValueOnce({
      driverError: { code: 'ER_DUP_ENTRY' },
    });

    await expect(
      service.create({
        client_id: 'cfa63b35-4379-423a-b99f-2fa88019b21f',
        restaurante_id: 'restaurante-1',
        usuario_id: 'usuario-1',
      }),
    ).resolves.toBe(existente);
  });
});

describe('Bitacora creation order migration (no database)', () => {
  it('adds the missing column and index without changing or deleting evidence', async () => {
    const conn = { execute: jest.fn().mockResolvedValue([[]]), query: jest.fn() };
    const log = jest.spyOn(console, 'log').mockImplementation(() => {});
    try {
      await migrateBitacoraCreatedAt(conn as any);
      expect(conn.query.mock.calls.map(([sql]) => sql)).toEqual([
        'ALTER TABLE `bitacoras` ADD COLUMN `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)',
        'CREATE INDEX `idx_bitacoras_fecha_creacion` ON `bitacoras` (`fecha`, `created_at`, `id`)',
      ]);
    } finally { log.mockRestore(); }
  });

  it('is idempotent and preserves an existing historical created_at', async () => {
    const conn = { execute: jest.fn().mockResolvedValue([[{ exists: true }]]), query: jest.fn() };
    await migrateBitacoraCreatedAt(conn as any);
    expect(conn.query).not.toHaveBeenCalled();
  });
});
