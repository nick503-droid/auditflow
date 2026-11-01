import { DataSource, Repository } from 'typeorm';
import { BitacorasService } from './bitacoras.service';
import { Bitacora } from './entities/bitacora.entity';
import { EvidenciaBitacora } from './entities/evidencia-bitacora.entity';
import { Usuario } from '../usuarios/entities/usuario.entity';
import { Restaurante } from '../restaurantes/entities/restaurante.entity';

// Metadatos MySQL reales, sin abrir conexiones ni modificar datos del usuario.
class MetadataOnlySource extends DataSource {
  async loadMetadata() { await this.buildMetadatas(); }
}

describe('Bitácoras: conservar el restaurante seleccionado', () => {
  let source: MetadataOnlySource;
  beforeAll(async () => {
    source = new MetadataOnlySource({
      type: 'mysql', database: 'fixture',
      entities: [Bitacora, EvidenciaBitacora, Usuario, Restaurante],
    });
    await source.loadMetadata();
  });

  function fixture() {
    const restaurantes = {
      san: { id: 'san', nombre: 'San Bernardino' },
      covina: { id: 'covina', nombre: 'Covina' },
      norco: { id: 'norco', nombre: 'Norco' },
    };
    const row = {
      id: 'b1', restaurante_id: 'san', usuario_id: 'u1',
      descripcion: 'Texto existente', hora: '2:40 pm', codigo: 'ABC123',
      client_id: 'client-original', version: 1,
      created_at: new Date('2026-10-24T20:00:00Z'),
      updated_at: new Date('2026-10-24T20:00:00Z'),
    };
    const evidence = [{ id: 'ev1', evidencia_url: '/evidencias/prueba.mp4' }];
    const snapshot = () => ({ ...row,
      restaurante: { ...restaurantes[row.restaurante_id] },
      usuario: { id: row.usuario_id }, evidencias: [...evidence],
    });
    const repo = {
      findOne: jest.fn(async () => snapshot()),
      find: jest.fn(async () => [snapshot()]),
      // Reproduce el comportamiento de save con relaciones ya cargadas usando
      // ColumnMetadata real. Antes del arreglo restaurante_id volvía a 'san'.
      save: jest.fn(async (entity) => {
        const column = source.getMetadata(Bitacora).findColumnWithPropertyName('restaurante_id')!;
        Object.assign(row, entity, { restaurante_id: column.getEntityValue(entity) });
        return snapshot();
      }),
      update: jest.fn(async (_id, changes) => {
        Object.assign(row, changes);
        row.version += 1;
        row.updated_at = new Date('2026-10-24T20:00:01Z');
        return { affected: 1 };
      }),
    };
    const service = new BitacorasService(repo as unknown as Repository<Bitacora>, {} as any, {} as any, {} as any);
    return { row, repo, service, evidence };
  }

  it('guarda Covina aunque findOne haya cargado la relación San Bernardino', async () => {
    const f = fixture();
    const result = await f.service.update('b1', { restaurante_id: 'covina' });
    expect(result).toMatchObject({ restaurante_id: 'covina', restaurante: { id: 'covina', nombre: 'Covina' } });
    expect(f.repo.save).not.toHaveBeenCalled();
    expect(f.repo.update).toHaveBeenCalledWith('b1', { restaurante_id: 'covina' });
  });

  it('mantiene la selección al reabrir, recargar el día y consultar los deltas', async () => {
    const f = fixture();
    await f.service.update('b1', { restaurante_id: 'covina' });
    expect(await f.service.findOne('b1')).toMatchObject({ restaurante_id: 'covina' });
    expect(await f.service.findPorFecha('2026-10-24')).toEqual([
      expect.objectContaining({ restaurante: expect.objectContaining({ nombre: 'Covina' }) }),
    ]);
    expect(await f.service.findDesde('2026-10-24', new Date('2026-10-24T20:00:00Z'))).toEqual([
      expect.objectContaining({ restaurante_id: 'covina', version: 2 }),
    ]);
  });

  it('conserva el último cambio confirmado entre varios restaurantes', async () => {
    const f = fixture();
    for (const restaurante_id of ['covina', 'norco', 'san', 'covina']) {
      expect(await f.service.update('b1', { restaurante_id })).toMatchObject({ restaurante_id });
    }
    expect(f.row.restaurante_id).toBe('covina');
  });

  it('editar otro campo desde otro cliente no restaura la relación anterior', async () => {
    const f = fixture();
    await f.service.update('b1', { restaurante_id: 'covina' });
    const result = await f.service.update('b1', { descripcion: 'Texto de otra PC' });
    expect(result).toMatchObject({ restaurante_id: 'covina', descripcion: 'Texto de otra PC' });
    expect(f.row.hora).toBe('2:40 pm');
    expect(f.row.codigo).toBe('ABC123');
    expect(result!.evidencias).toEqual(f.evidence);
    expect(f.row.created_at.toISOString()).toBe('2026-10-24T20:00:00.000Z');
  });

  it('no cambia client_id ni rebaja la versión con metadatos de una PC', async () => {
    const f = fixture();
    f.row.version = 7;
    await f.service.update('b1', { restaurante_id: 'covina', client_id: 'otro', version: 1 });
    expect(f.row).toMatchObject({ client_id: 'client-original', version: 8, restaurante_id: 'covina' });
    expect(f.repo.update.mock.calls[0][1]).toEqual({ restaurante_id: 'covina' });
  });

  it('conserva el resultado nulo para una bitácora inexistente y no escribe un PATCH vacío', async () => {
    const f = fixture();
    f.repo.findOne.mockResolvedValueOnce(null as any);
    expect(await f.service.update('no-existe', { restaurante_id: 'covina' })).toBeNull();
    expect(f.repo.update).not.toHaveBeenCalled();
    await expect(f.service.update('b1', { client_id: 'ignorar', version: 1 })).resolves.toMatchObject({ version: 1 });
    expect(f.repo.update).not.toHaveBeenCalled();
  });

  it('el UPDATE real usa la FK nueva y actualiza el cursor y la versión automáticamente', () => {
    const [sql, params] = source.createQueryBuilder().update(Bitacora)
      .set({ restaurante_id: 'covina' }).where('id = :id', { id: 'b1' }).getQueryAndParameters();
    expect(sql).toContain('`restaurante_id` = ?');
    expect(sql).toContain('`version` = `version` + 1');
    expect(sql).toContain('`updated_at` = CURRENT_TIMESTAMP');
    expect(sql).not.toContain('created_at');
    expect(params).toEqual(['covina', 'b1']);
  });
});
