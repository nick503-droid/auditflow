import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Restaurante } from './entities/restaurante.entity';
import { CreateRestauranteDto } from './dto/create-restaurante.dto';
import { UpdateRestauranteDto } from './dto/update-restaurante.dto';

@Injectable()
export class RestaurantesService {
  constructor(
    @InjectRepository(Restaurante)
    private restaurantesRepo: Repository<Restaurante>,
  ) {}

  findAll(incluirInactivos = false) {
    return this.restaurantesRepo.find({
      where: incluirInactivos ? {} : { activo: 1 },
      order: { nombre: 'ASC', id: 'ASC' },
    });
  }

  findOne(id: string) {
    return this.restaurantesRepo.findOneBy({ id });
  }

  create(dto: CreateRestauranteDto) {
    const nuevo = this.restaurantesRepo.create({
      nombre: this.nombreValido(dto.nombre),
    });
    return this.restaurantesRepo.save(nuevo);
  }

  async update(id: string, dto: UpdateRestauranteDto) {
    if (!(await this.findOne(id)))
      throw new NotFoundException('Restaurante no encontrado.');
    const cambios: Partial<Restaurante> = {};
    if (dto.nombre !== undefined)
      cambios.nombre = this.nombreValido(dto.nombre);
    if (dto.activo !== undefined) {
      if (dto.activo !== 0 && dto.activo !== 1)
        throw new BadRequestException('Estado no válido.');
      cambios.activo = dto.activo;
    }
    if (Object.keys(cambios).length)
      await this.restaurantesRepo.update(id, cambios);
    return this.findOne(id);
  }

  remove(id: string) {
    return this.update(id, { activo: 0 });
  }

  private nombreValido(value: string) {
    if (
      typeof value !== 'string' ||
      !value.trim() ||
      value.trim().length > 255
    ) {
      throw new BadRequestException(
        'El nombre es obligatorio y admite hasta 255 caracteres.',
      );
    }
    return value.trim();
  }
}
