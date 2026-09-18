import { Entity, PrimaryGeneratedColumn, Column, DeleteDateColumn } from 'typeorm';

@Entity('restaurantes')
export class Restaurante {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ type: 'varchar' })
  nombre: string;

  @DeleteDateColumn({ name: 'deleted_at' })
  deleted_at: Date;
}