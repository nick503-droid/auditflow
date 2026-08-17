import { Injectable } from '@nestjs/common';
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

  findAll() {
    return this.restaurantesRepo.find();
  }

  findOne(id: string) {
    return this.restaurantesRepo.findOneBy({ id });
  }

  create(dto: CreateRestauranteDto) {
    const nuevo = this.restaurantesRepo.create(dto);
    return this.restaurantesRepo.save(nuevo);
  }

  async update(id: string, dto: UpdateRestauranteDto) {
    await this.restaurantesRepo.update(id, dto);
    return this.findOne(id);
  }

  remove(id: string) {
    return this.restaurantesRepo.softDelete(id); // soft delete real
  }
}