import { IsUUID, IsString, IsNotEmpty, IsBoolean, IsOptional, IsInt, IsISO8601 } from 'class-validator';

export class CreateEvidenciaReporteDto {
  @IsUUID()
  reporte_id: string;

  @IsString()
  @IsNotEmpty()
  evidencia_url: string;

  @IsOptional()
  @IsBoolean()
  con_audio?: boolean;

  @IsInt()
  orden_reproduccion: number;

  @IsOptional()
  @IsISO8601()
  agregado_en?: string;
}
