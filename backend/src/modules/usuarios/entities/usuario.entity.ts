import { Entity, PrimaryGeneratedColumn, Column, DeleteDateColumn } from 'typeorm';

@Entity('usuarios')
export class Usuario {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ type: 'varchar' })
  nombre: string;

  @Column({ type: 'tinyint', default: 1 })
  activo: number;

  @DeleteDateColumn()
  deleted_at: Date; // Soft delete automático de TypeORM
}
