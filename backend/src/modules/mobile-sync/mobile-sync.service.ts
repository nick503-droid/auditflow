import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Bitacora } from '../bitacoras/entities/bitacora.entity';
import { EvidenciaBitacora } from '../bitacoras/entities/evidencia-bitacora.entity';
import { Reporte } from '../reportes/entities/reporte.entity';
import { EvidenciaReporte } from '../evidencias-reporte/entities/evidencia-reporte.entity';
import { StorageService } from '../../common/storage/storage.service';

@Injectable()
export class MobileSyncService {
  private readonly logger = new Logger(MobileSyncService.name);

  constructor(
    @InjectRepository(Bitacora) private bitacorasRepo: Repository<Bitacora>,
    @InjectRepository(EvidenciaBitacora) private evidenciasBitacoraRepo: Repository<EvidenciaBitacora>,
    @InjectRepository(Reporte) private reportesRepo: Repository<Reporte>,
    @InjectRepository(EvidenciaReporte) private evidenciasReporteRepo: Repository<EvidenciaReporte>,
    private storageService: StorageService,
  ) {}

  /**
   * Valida un código de 6 caracteres buscando primero en Bitácoras y luego
   * en Reportes. Retorna un resumen plano con los campos que necesita la App
   * Móvil para mostrar el destino de la evidencia.
   *
   * OPTIMIZACIÓN N+1:
   *  - Usa QueryBuilder con .select() estricto: solo trae los campos necesarios
   *    en lugar de hidratar el objeto completo con todas sus relaciones.
   *  - El conteo de evidencias se obtiene via subquery COUNT en la misma query,
   *    eliminando la carga de todo el array de evidencias en memoria.
   *  - Ambas búsquedas se benefician del índice idx_bitacoras_codigo /
   *    idx_reportes_codigo creado en las entidades.
   */
  async validarCodigo(codigo: string) {
    const codToUpper = codigo.toUpperCase();

    // ── 1. Buscar en Bitácoras ────────────────────────────────────────────────
    // Selección estricta de campos + subquery COUNT para evidencias_count.
    // Un solo round-trip a la BD; sin cargar restaurante ni usuario completos.
    const bitacora = await this.bitacorasRepo
      .createQueryBuilder('b')
      .select([
        'b.id            AS id',
        'b.fecha         AS fecha',
        'b.hora          AS hora',
        'b.descripcion   AS descripcion',
        'r.nombre        AS restaurante',
        'u.nombre        AS usuario',
        // Subquery COUNT — evita cargar el array completo de evidencias
        '(SELECT COUNT(*) FROM evidencias_bitacora eb WHERE eb.bitacora_id = b.id AND eb.deleted_at IS NULL) AS evidencias_count',
      ])
      .innerJoin('b.restaurante', 'r')
      .innerJoin('b.usuario', 'u')
      .where('b.codigo = :codigo', { codigo: codToUpper })
      .orderBy('b.fecha', 'DESC')
      .limit(1)
      .getRawOne<{
        id: string;
        fecha: Date;
        hora: string;
        descripcion: string;
        restaurante: string;
        usuario: string;
        evidencias_count: string; // MySQL devuelve COUNT como string
      }>();

    if (bitacora) {
      return {
        valido: true,
        tipo: 'bitacora',
        id: bitacora.id,
        fecha: bitacora.fecha,
        restaurante: bitacora.restaurante ?? 'Sin Restaurante',
        hora: bitacora.hora ?? '--:--',
        descripcion: bitacora.descripcion ?? 'Sin descripción',
        usuario: bitacora.usuario ?? 'Usuario Desconocido',
        evidencias_count: Number(bitacora.evidencias_count),
      };
    }

    // ── 2. Buscar en Reportes ─────────────────────────────────────────────────
    const reporte = await this.reportesRepo
      .createQueryBuilder('rep')
      .select([
        'rep.id     AS id',
        'rep.titulo AS titulo',
        '(SELECT COUNT(*) FROM evidencias_reporte er WHERE er.reporte_id = rep.id AND er.deleted_at IS NULL) AS evidencias_count',
      ])
      .where('rep.codigo = :codigo', { codigo: codToUpper })
      .limit(1)
      .getRawOne<{
        id: string;
        titulo: string;
        evidencias_count: string;
      }>();

    if (reporte) {
      return {
        valido: true,
        tipo: 'reporte',
        id: reporte.id,
        titulo: reporte.titulo ?? 'Reporte Sin Título',
        evidencias_count: Number(reporte.evidencias_count),
      };
    }

    // No existe en ninguna tabla
    throw new NotFoundException('Código de vinculación inválido o expirado.');
  }

  /**
   * Mueve el archivo de /temp a su carpeta final y lo vincula a la BD.
   * Aplica Rollback físico si la BD falla.
   */
  async vincularEvidencia(codigo: string, nombreTemp: string, conAudio: boolean) {
    const info = await this.validarCodigo(codigo);
    
    let prefijoDestino = '';
    
    // Calcular prefijo de destino basado en las reglas locales
    if (info.tipo === 'bitacora') {
      // Convertir Date a "MM-DD-YYYY" o mantener si es string ISO
      // Asumimos que bitacora.fecha es 'YYYY-MM-DD' o Date
      let dateObj = new Date(info.fecha || new Date());
      if (isNaN(dateObj.getTime())) dateObj = new Date(); // Fallback preventivo
      
      const mm = String(dateObj.getMonth() + 1).padStart(2, '0');
      const dd = String(dateObj.getDate()).padStart(2, '0');
      const yyyy = dateObj.getFullYear();
      
      prefijoDestino = `bitacoras/${mm}-${dd}-${yyyy}`;
    } else {
      // Para reportes, la regla es unificar o "reportes/[CODIGO] Titulo"
      // Usaremos la regla solicitada: "reportes/[CODIGO] Titulo"
      const tituloLimpio = (info.titulo || 'Reporte').replace(/[^a-zA-Z0-9\s.\-_]/g, '').trim().substring(0, 50);
      prefijoDestino = `reportes/[${codigo.toUpperCase()}] ${tituloLimpio}`;
    }
    
    // 1. Mover archivo de /temp a destino final
    let urlFinal = '';
    try {
      urlFinal = await this.storageService.moverDeTemp(nombreTemp, prefijoDestino);
    } catch (error) {
      this.logger.error(`Error al mover archivo temporal: ${error.message}`);
      throw error;
    }
    
    // 2. Insertar en la Base de Datos con Rollback en caso de falla
    try {
      if (info.tipo === 'bitacora') {
        const nueva = this.evidenciasBitacoraRepo.create({
          bitacora_id: info.id,
          evidencia_url: urlFinal,
          con_audio: conAudio,
        });
        await this.evidenciasBitacoraRepo.save(nueva);
      } else {
        const nueva = this.evidenciasReporteRepo.create({
          reporte_id: info.id,
          evidencia_url: urlFinal,
          con_audio: conAudio,
          orden_reproduccion: 0,
        });
        await this.evidenciasReporteRepo.save(nueva);
      }
      
      return { exito: true, evidencia_url: urlFinal };
      
    } catch (dbError) {
      this.logger.error(`Error en BD. Aplicando Rollback físico a ${urlFinal}`);
      // ROLLBACK: Eliminar el archivo físico recién movido
      await this.storageService.eliminarArchivo(urlFinal);
      throw dbError; // Lanzar el error para que el controller devuelva 500
    }
  }
}
