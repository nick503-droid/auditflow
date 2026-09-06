import { IsUUID, IsString, IsOptional, IsBoolean, IsDateString, IsEnum } from 'class-validator';
import { NivelUrgencia } from '../entities/bitacora.entity';

export class CreateBitacoraDto {
  /**
   * Identificador generado por el cliente (UUID v4) para garantizar idempotencia.
   * Si se envía y ya existe en la base de datos, el servidor ignorará la creación.
   */
  @IsOptional()
  @IsUUID()
  client_id?: string;

  @IsUUID()
  restaurante_id: string;

  @IsUUID()
  usuario_id: string;

  /**
   * Descripción de la bitácora. Opcional al crear para permitir que el
   * vigilante genere el código de evidencia de inmediato (solo con
   * restaurante seleccionado) y complete la descripción después.
   */
  @IsOptional()
  @IsString()
  descripcion?: string;

  @IsOptional()
  @IsString()
  evidencia_url?: string;

  @IsOptional()
  @IsBoolean()
  con_audio?: boolean;

  /**
   * Fecha de la bitácora (YYYY-MM-DD). Si no se envía, el servicio
   * usa la fecha actual del servidor.
   */
  @IsOptional()
  @IsDateString()
  fecha?: string;

  /**
   * Hora ingresada manualmente por el vigilante (texto libre).
   * Opcional al crear para el flujo de evidencia anticipada.
   */
  @IsOptional()
  @IsString()
  hora?: string;

  @IsOptional()
  @IsEnum(NivelUrgencia)
  urgencia?: NivelUrgencia;
}