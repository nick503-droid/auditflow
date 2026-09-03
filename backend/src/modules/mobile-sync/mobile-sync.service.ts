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
   * Busca un código en Bitácoras o Reportes.
   * Retorna información básica para que la app móvil sepa si es válido.
   */
  async validarCodigo(codigo: string) {
    const codToUpper = codigo.toUpperCase();
    
    // 1. Buscar en Bitácoras
    const bitacora = await this.bitacorasRepo.findOne({
      where: { codigo: codToUpper },
      order: { fecha: 'DESC' },
      relations: { restaurante: true, usuario: true, evidencias: true },
    });
    
    if (bitacora) {
      return {
        valido: true,
        tipo: 'bitacora',
        id: bitacora.id,
        fecha: bitacora.fecha,
        // Datos planos extraídos de las relaciones
        restaurante: bitacora.restaurante?.nombre || 'Sin Restaurante',
        hora: bitacora.hora || '--:--',
        descripcion: bitacora.descripcion || 'Sin descripción',
        usuario: bitacora.usuario?.nombre || 'Usuario Desconocido',
        evidencias_count: bitacora.evidencias?.length || 0,
      };
    }
    
    // 2. Buscar en Reportes
    const reporte = await this.reportesRepo.findOne({
      where: { codigo: codToUpper },
      relations: { evidencias: true },
    });
    
    if (reporte) {
      return {
        valido: true,
        tipo: 'reporte',
        id: reporte.id,
        titulo: reporte.titulo || 'Reporte Sin Título',
        evidencias_count: reporte.evidencias?.length || 0,
      };
    }
    
    // No existe
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
