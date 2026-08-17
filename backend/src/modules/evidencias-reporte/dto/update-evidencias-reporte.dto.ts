import { PartialType } from '@nestjs/mapped-types';
import { CreateEvidenciaReporteDto } from './create-evidencias-reporte.dto';

export class UpdateEvidenciasReporteDto extends PartialType(CreateEvidenciaReporteDto) {}
