import { PartialType } from '@nestjs/mapped-types';
import { CreateRestauranteDto } from './create-restaurante.dto';
import { IsIn, IsOptional } from 'class-validator';

export class UpdateRestauranteDto extends PartialType(CreateRestauranteDto) {
  @IsOptional()
  @IsIn([0, 1])
  activo?: number;
}
