import { BadRequestException, NotFoundException } from '@nestjs/common';
import { DeepPartial, ObjectLiteral, Repository } from 'typeorm';

type OrderedEvidence = ObjectLiteral & {
  agregado_en?: Date | null;
  secuencia_adicion?: string | null;
};

/** Orden definitivo de nuevas evidencias. Las antiguas conservan un fallback. */
export function ordenarEvidencias<T extends OrderedEvidence>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const ta = a.agregado_en ? new Date(a.agregado_en).getTime() : 0;
    const tb = b.agregado_en ? new Date(b.agregado_en).getTime() : 0;
    if (ta !== tb) return ta - tb;
    if (ta) {
      const sa = BigInt(a.secuencia_adicion || 0), sb = BigInt(b.secuencia_adicion || 0);
      if (sa !== sb) return sa < sb ? -1 : 1;
    }
    return (a.orden_reproduccion || 0) - (b.orden_reproduccion || 0)
      || String(a.creado_en || '').localeCompare(String(b.creado_en || ''))
      || String(a.id || '').localeCompare(String(b.id || ''));
  });
}

export function ordenarAdjuntas<T extends { evidencias?: OrderedEvidence[] }>(parent: T | null): T | null {
  if (parent?.evidencias) parent.evidencias = ordenarEvidencias(parent.evidencias);
  return parent;
}

/** Serializa sólo las altas del mismo padre, nunca toda la tabla.
 * La fecha original no cambia en reintentos y la secuencia no depende de COUNT
 * ni de UUIDs. El touch del padre y la evidencia se confirman juntos.
 */
export async function registrarEvidenciaOrdenada<T extends OrderedEvidence>(
  repo: Repository<T>, parentRepo: Repository<any>, parentId: string,
  foreignKey: 'bitacora_id' | 'reporte_id', values: DeepPartial<T>,
  agregadoEn?: string | Date,
): Promise<T> {
  const fecha = agregadoEn ? new Date(agregadoEn) : new Date();
  if (!Number.isFinite(fecha.getTime())) throw new BadRequestException('Fecha de incorporación inválida.');
  return repo.manager.transaction(async (manager) => {
    const parents = manager.getRepository(parentRepo.target);
    const parent = await parents.findOne({
      where: { id: parentId }, lock: { mode: 'pessimistic_write' },
    });
    if (!parent) throw new NotFoundException('No existe el destino de la evidencia.');
    const children = manager.getRepository(repo.target);
    const existente = await children.findOne({
      where: { [foreignKey]: parentId, evidencia_url: (values as ObjectLiteral).evidencia_url } as any,
    });
    if (existente) return existente;
    const max = await children.createQueryBuilder('ev').withDeleted()
      .select('MAX(ev.secuencia_adicion)', 'ultimo')
      .where(`ev.${foreignKey} = :id`, { id: parentId })
      .getRawOne<{ ultimo: string | null }>();
    const nueva = children.create({
      ...values,
      agregado_en: fecha,
      secuencia_adicion: String(BigInt(max?.ultimo || 0) + 1n),
    } as DeepPartial<T>);
    const evidencia = await children.save(nueva);
    await parents.update(parentId, { updated_at: new Date() });
    return evidencia;
  });
}
