import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  ManyToOne,
  JoinColumn,
  DeleteDateColumn,
} from 'typeorm';
import { Usuario } from '../../usuarios/entities/usuario.entity';
import { Restaurante } from '../../restaurantes/entities/restaurante.entity';

export enum NivelUrgencia {
  LOW = 'low',
  MEDIUM = 'medium',
  CRITICAL = 'critical',
}

@Entity('bitacoras')
export class Bitacora {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @ManyToOne(() => Restaurante)
  @JoinColumn({ name: 'restaurante_id' })
  restaurante: Restaurante;

  @Column({ name: 'restaurante_id' })
  restaurante_id: string;

  @ManyToOne(() => Usuario)
  @JoinColumn({ name: 'usuario_id' })
  usuario: Usuario;

  @Column({ name: 'usuario_id' })
  usuario_id: string;

  @Column({ type: 'text' })
  descripcion: string;

  @Column({ type: 'varchar', nullable: true })
  evidencia_url: string;

  @Column({ type: 'tinyint', default: 0 })
  con_audio: boolean;

  @Column({ type: 'date', default: () => 'CURRENT_DATE' })
  fecha: Date;

  @Column({ type: 'varchar', length: 20, default: '00:00' })
  hora: string;

  @Column({ type: 'enum', enum: NivelUrgencia, default: NivelUrgencia.LOW })
  urgencia: NivelUrgencia;

  @Column({ type: 'varchar', length: 6, default: 'MIGRAC' })
  codigo: string;

  @DeleteDateColumn()
  deleted_at: Date;
}