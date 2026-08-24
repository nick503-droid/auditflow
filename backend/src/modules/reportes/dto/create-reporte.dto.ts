import { IsString, IsOptional, IsNotEmpty } from 'class-validator';

export class CreateReporteDto {
  @IsString()
  @IsNotEmpty()
  usuario_id: string;

  @IsString()
  @IsNotEmpty()
  restaurante_id: string;

  @IsString()
  @IsOptional()
  titulo?: string;

  @IsString()
  @IsOptional()
  notas_finales?: string;
  
  @IsOptional()
  fecha_jornada?: any;
}