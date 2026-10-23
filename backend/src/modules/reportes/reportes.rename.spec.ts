import { ConflictException } from '@nestjs/common';
import { ReportesService } from './reportes.service';

describe('Reportes: renombrado y versión atómica', () => {
  function fixture() {
    const row = { id: 'r1', titulo: 'Original', notas_finales: 'Notas existentes', version: 1 };
    const queries: any[] = [];
    const repo = {
      findOne: jest.fn(async () => ({ ...row })),
      createQueryBuilder: jest.fn(() => {
        let expected: number;
        let changes: any;
        const builder = {
          update: jest.fn().mockReturnThis(),
          set: jest.fn((value) => { changes = value; return builder; }),
          where: jest.fn((_sql, params) => { expected = params.version; return builder; }),
          execute: jest.fn(async () => {
            // Emular el UPDATE ... WHERE version del servidor, no un save ciego.
            if (row.version !== expected) return { affected: 0 };
            if (changes.titulo !== undefined) row.titulo = changes.titulo;
            if (changes.notas_finales !== undefined) row.notas_finales = changes.notas_finales;
            row.version += 1;
            return { affected: 1 };
          }),
        };
        queries.push(builder);
        return builder;
      }),
    };
    return { row, repo, queries, service: new ReportesService(repo as any, {} as any, {} as any) };
  }

  it('acepta renombrar un reporte recién creado con su versión actual', async () => {
    const f = fixture();
    const result = await f.service.update('r1', { titulo: 'Nuevo', version: 1 });
    expect(result).toMatchObject({ titulo: 'Nuevo', version: 2, notas_finales: 'Notas existentes' });
    expect(f.queries[0].where).toHaveBeenCalledWith('id = :id AND version = :version', { id: 'r1', version: 1 });
  });

  it('mantiene el rechazo de clientes que no envían versión', async () => {
    const f = fixture();
    await expect(f.service.update('r1', { titulo: 'Nuevo' })).rejects.toBeInstanceOf(ConflictException);
    expect(f.repo.createQueryBuilder).not.toHaveBeenCalled();
    expect(f.row.titulo).toBe('Original');
  });

  it('dos PCs con la misma versión no pueden sobrescribir el nombre silenciosamente', async () => {
    const f = fixture();
    const results = await Promise.allSettled([
      f.service.update('r1', { titulo: 'PC A', version: 1 }),
      f.service.update('r1', { titulo: 'PC B', version: 1 }),
    ]);
    expect(results.filter(r => r.status === 'fulfilled')).toHaveLength(1);
    const rejected = results.find(r => r.status === 'rejected') as PromiseRejectedResult;
    expect(rejected.reason).toBeInstanceOf(ConflictException);
    expect(f.row.version).toBe(2);
    expect(f.row.notas_finales).toBe('Notas existentes');
  });

  it('renombrar con una versión posterior conserva notas guardadas entretanto', async () => {
    const f = fixture();
    await f.service.update('r1', { notas_finales: 'Notas de otra PC', version: 1 });
    const result = await f.service.update('r1', { titulo: 'Nuevo', version: 2 });
    expect(result).toMatchObject({ titulo: 'Nuevo', version: 3, notas_finales: 'Notas de otra PC' });
  });
});
