import { IsString, IsNotEmpty } from 'class-validator';

export class CreateRestauranteDto {
  @IsString()
  @IsNotEmpty()
  nombre: string;
}