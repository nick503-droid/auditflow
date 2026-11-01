import { DataSource } from 'typeorm';
import { ordenarEvidencias, ordenarAdjuntas, registrarEvidenciaOrdenada } from './evidence-order';
import { Bitacora } from '../modules/bitacoras/entities/bitacora.entity';
import { EvidenciaBitacora } from '../modules/bitacoras/entities/evidencia-bitacora.entity';
import { Reporte } from '../modules/reportes/entities/reporte.entity';
import { ReportesService } from '../modules/reportes/reportes.service';
import { EvidenciaReporte } from '../modules/evidencias-reporte/entities/evidencia-reporte.entity';
import { Usuario } from '../modules/usuarios/entities/usuario.entity';
import { Restaurante } from '../modules/restaurantes/entities/restaurante.entity';
import { EvidenciasReporteService } from '../modules/evidencias-reporte/evidencias-reporte.service';
import { BitacorasService } from '../modules/bitacoras/bitacoras.service';
import { MobileSyncService } from '../modules/mobile-sync/mobile-sync.service';
import { migrateEvidenceOrder } from '../../scripts/migrate-evidence-order';

const FIRST = '2026-11-01T10:00:00.000Z';
const SECOND = '2026-11-01T10:00:03.000Z';

// Emula el bloqueo de filas y rollback para probar el contrato transaccional,
// sin conectarse a MySQL ni leer datos de producción.
function fixture() {
  const rows: any[] = [];
  const events: string[] = [];
  let queue = Promise.resolve();
  let parentExists = true;
  const parents = {
    target: 'parent',
    findOne: jest.fn(async (options) => {
      expect(options.lock).toEqual({ mode: 'pessimistic_write' });
      events.push('lock');
      return parentExists ? { id: options.where.id } : null;
    }),
    update: jest.fn(async () => { events.push('touch'); return { affected: 1 }; }),
  };
  const children = {
    target: 'evidence', manager: {} as any,
    findOne: jest.fn(async ({ where }) => rows.find(row => !row.deleted_at && Object.entries(where).every(([k, v]) => row[k] === v)) || null),
    create: jest.fn(value => value),
    save: jest.fn(async value => { events.push('save'); const row = { ...value, id: `id-${rows.length}` }; rows.push(row); return row; }),
    createQueryBuilder: jest.fn(() => {
      let parentId: string, foreignKey: string;
      const builder = {
        withDeleted: jest.fn().mockReturnThis(), select: jest.fn().mockReturnThis(),
        where: jest.fn((sql, params) => { parentId = params.id; foreignKey = sql.includes('bitacora_id') ? 'bitacora_id' : 'reporte_id'; return builder; }),
        getRawOne: jest.fn(async () => {
          events.push('max');
          return { ultimo: String(rows.filter(row => row[foreignKey] === parentId)
            .reduce((max, row) => BigInt(row.secuencia_adicion || 0) > max ? BigInt(row.secuencia_adicion) : max, 0n)) };
        }),
      };
      return builder;
    }),
  };
  const manager = { getRepository: (target) => target === 'parent' ? parents : children };
  children.manager.transaction = jest.fn(callback => {
    const task = queue.then(async () => {
      const before = [...rows];
      try { return await callback(manager); }
      catch (error) { rows.splice(0, rows.length, ...before); throw error; }
    });
    queue = task.then(() => undefined, () => undefined);
    return task;
  });
  const add = (url: string, added = FIRST, parentId = 'p1') => registrarEvidenciaOrdenada(
    children as any, parents as any, parentId, 'reporte_id', { reporte_id: parentId, evidencia_url: url }, added,
  );
  return { rows, events, parents, children, add, noParent: () => { parentExists = false; } };
}

describe('Orden permanente de evidencias nuevas', () => {
  it('respeta incorporación y no llegada a la red, UUID ni orden_reproduccion', () => {
    const first = { id: 'z', agregado_en: new Date(FIRST), secuencia_adicion: '8', orden_reproduccion: 99 };
    const second = { id: 'a', agregado_en: new Date(SECOND), secuencia_adicion: '1', orden_reproduccion: 0 };
    expect(ordenarEvidencias([second, first])).toEqual([first, second]);
    expect(ordenarAdjuntas({ evidencias: [second, first] })!.evidencias).toEqual([first, second]);
  });

  it('desempata con secuencias numéricas, no con UUIDs', () => {
    const rows = [10, 2].map(n => ({ agregado_en: new Date(FIRST), secuencia_adicion: String(n) }));
    expect(ordenarEvidencias(rows).map(r => r.secuencia_adicion)).toEqual(['2', '10']);
  });

  it('dos clientes con la misma fecha obtienen secuencias distintas bajo bloqueo', async () => {
    const f = fixture();
    const results = await Promise.all([f.add('first.jpg'), f.add('second.jpg')]);
    expect(results.map(r => r.secuencia_adicion)).toEqual(['1', '2']);
    expect(f.events).toEqual(['lock', 'max', 'save', 'touch', 'lock', 'max', 'save', 'touch']);
    expect(results.map(r => r.agregado_en!.toISOString())).toEqual([FIRST, FIRST]);
  });

  it('un reintento no cambia fecha, secuencia ni duplica la evidencia', async () => {
    const f = fixture();
    const first = await f.add('first.jpg');
    expect(await f.add('first.jpg', SECOND)).toEqual(first);
    expect(f.rows).toHaveLength(1);
    expect(f.parents.update).toHaveBeenCalledTimes(1);
  });

  it('los soft-deletes no hacen reutilizar la secuencia y otros padres son independientes', async () => {
    const f = fixture();
    await f.add('first.jpg'); f.rows[0].deleted_at = new Date();
    expect((await f.add('second.jpg')).secuencia_adicion).toBe('2');
    expect((await f.add('third.jpg', FIRST, 'p2')).secuencia_adicion).toBe('1');
  });

  it('revierte la inserción si no se puede notificar al padre', async () => {
    const f = fixture();
    f.parents.update.mockRejectedValueOnce(new Error('DB fixture'));
    await expect(f.add('first.jpg')).rejects.toThrow('DB fixture');
    expect(f.rows).toHaveLength(0);
  });

  it('no escribe fechas inválidas ni evidencias de padres inexistentes', async () => {
    const f = fixture();
    await expect(f.add('first.jpg', 'fecha inválida')).rejects.toThrow('Fecha de incorporación inválida');
    expect(f.children.manager.transaction).not.toHaveBeenCalled();
    f.noParent();
    await expect(f.add('first.jpg')).rejects.toThrow('No existe el destino');
    expect(f.children.save).not.toHaveBeenCalled();
  });

  it('el alta de reportes PC guarda su fecha original y toca el padre', async () => {
    const f = fixture();
    const service = new EvidenciasReporteService(f.children as any, f.parents as any, {} as any, {} as any);
    const row = await service.create({ reporte_id: 'p1', evidencia_url: 'first.jpg', orden_reproduccion: 0, agregado_en: FIRST });
    expect(row.agregado_en!.toISOString()).toBe(FIRST);
    expect(row.secuencia_adicion).toBe('1');
    expect(f.parents.update).toHaveBeenCalled();
  });

  it('el alta de bitácoras PC pasa por el mismo contrato', async () => {
    const f = fixture();
    const service = new BitacorasService(f.parents as any, f.children as any, {} as any, {} as any);
    jest.spyOn(service, 'findPorCodigo').mockResolvedValue({ id: 'p1' } as any);
    jest.spyOn(service, 'findOne').mockResolvedValue({ id: 'p1' } as any);
    await service.adjuntarEvidenciaPorCodigo('ABC123', 'first.jpg', false, FIRST);
    expect(f.rows[0]).toMatchObject({ bitacora_id: 'p1', agregado_en: new Date(FIRST), secuencia_adicion: '1' });
    expect(f.parents.update).toHaveBeenCalled();
  });

  it.each(['reporte', 'bitacora'])('el móvil %s usa fecha y secuencia, sin dar prioridad a orden cero', async (tipo) => {
    const f = fixture();
    const service = new MobileSyncService(f.parents as any, f.children as any, f.parents as any, f.children as any,
      { moverDeTemp: jest.fn(async () => 'first.jpg') } as any);
    jest.spyOn(service, 'validarCodigo').mockResolvedValue({ tipo, id: 'p1', fecha: '2026-11-01' } as any);
    await service.vincularEvidencia('ABC123', 'temp', false, FIRST);
    expect(f.rows[0]).toMatchObject({ agregado_en: new Date(FIRST), secuencia_adicion: '1' });
    expect(f.parents.update).toHaveBeenCalled();
  });

  it('clientes anteriores sin fecha siguen pudiendo adjuntar', async () => {
    const f = fixture();
    const service = new EvidenciasReporteService(f.children as any, f.parents as any, {} as any, {} as any);
    const row = await service.create({ reporte_id: 'p1', evidencia_url: 'first.jpg', orden_reproduccion: 0 });
    expect(row.agregado_en).toBeInstanceOf(Date);
  });

  it('los listados, reapertura y deltas devuelven el mismo orden', async () => {
    const first = { id: 'z', agregado_en: new Date(FIRST), secuencia_adicion: '2' };
    const second = { id: 'a', agregado_en: new Date(SECOND), secuencia_adicion: '1' };
    const repo = { find: jest.fn(async () => [{ id: 'p1', evidencias: [second, first] }]),
      findOne: jest.fn(async () => ({ id: 'p1', evidencias: [second, first] })) };
    const bit = new BitacorasService(repo as any, {} as any, {} as any, {} as any);
    const rep = new ReportesService(repo as any, {} as any, {} as any);
    for (const rows of [await bit.findAll(), await bit.findPorFecha('2026-11-01'),
      await bit.findDesde('2026-11-01', new Date(FIRST)), await rep.findAll()]) {
      expect(rows[0].evidencias.map(r => r.id)).toEqual(['z', 'a']);
    }
    expect((await bit.findOne('p1'))!.evidencias.map(r => r.id)).toEqual(['z', 'a']);
    expect((await rep.findOne('p1')).evidencias.map(r => r.id)).toEqual(['z', 'a']);
  });
});

describe('Schema aditivo, sin reconstruir historia', () => {
  it('la migración añade dos columnas y un índice por tabla y es idempotente', async () => {
    const conn = { execute: jest.fn().mockResolvedValue([[]]), query: jest.fn() };
    await migrateEvidenceOrder(conn as any);
    expect(conn.query).toHaveBeenCalledTimes(6);
    expect(conn.query.mock.calls.every(([sql]) => /^(ALTER TABLE .* ADD COLUMN|CREATE UNIQUE INDEX)/.test(sql))).toBe(true);
    expect(conn.query.mock.calls.map(([sql]) => sql).join('\n')).not.toMatch(/UPDATE|DELETE|DROP/);
    conn.execute.mockResolvedValue([[{ exists: true }]]); conn.query.mockClear();
    await migrateEvidenceOrder(conn as any);
    expect(conn.query).not.toHaveBeenCalled();
  });

  it('MySQL tiene precisión de milisegundos, índice único por padre y metadatos inmutables', async () => {
    class MetadataOnlySource extends DataSource { async loadMetadata() { await this.buildMetadatas(); } }
    const source = new MetadataOnlySource({ type: 'mysql', database: 'fixture',
      entities: [Bitacora, EvidenciaBitacora, Reporte, EvidenciaReporte, Usuario, Restaurante] });
    await source.loadMetadata();
    for (const target of [EvidenciaBitacora, EvidenciaReporte]) {
      const meta = source.getMetadata(target);
      expect(meta.findColumnWithPropertyName('agregado_en')).toMatchObject({ precision: 3, isNullable: true, isUpdate: false });
      expect(meta.findColumnWithPropertyName('secuencia_adicion')).toMatchObject({ type: 'bigint', isNullable: true, isUpdate: false });
      expect(meta.indices.some(i => i.isUnique && i.columns.some(c => c.propertyName === 'secuencia_adicion'))).toBe(true);
      const sql = source.createQueryBuilder().update(target).set({ con_audio: true, agregado_en: new Date(), secuencia_adicion: '99' }).where('id = :id', { id: 'fixture' }).getSql();
      expect(sql).not.toMatch(/agregado_en|secuencia_adicion/);
      const [insert, params] = source.createQueryBuilder().insert().into(target)
        .values({ evidencia_url: 'fixture.jpg', agregado_en: new Date(FIRST), secuencia_adicion: '99' })
        .getQueryAndParameters();
      expect(insert).toContain('`agregado_en`');
      expect(insert).toContain('`secuencia_adicion`');
      expect(params).toContain('99');
    }
  });
});
