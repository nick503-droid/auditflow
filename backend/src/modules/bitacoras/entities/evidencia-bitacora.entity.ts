import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  ManyToOne,
  JoinColumn,
  CreateDateColumn,
  DeleteDateColumn,
  Index,
} from 'typeorm';
import { Bitacora } from './bitacora.entity';

/**
 * Una bitácora puede tener múltiples evidencias (videos o fotos).
 * Se crea una fila aquí cada vez que alguien sube o vincula evidencia
 * usando el código corto de la bitácora — sin límite de cantidad.
 */
@Entity('evidencias_bitacora')
@Index('uq_ev_bitacora_adicion', ['bitacora_id', 'secuencia_adicion'], { unique: true })
export class EvidenciaBitacora {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @ManyToOne(() => Bitacora, (b) => b.evidencias, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'bitacora_id' })
  bitacora: Bitacora;

  @Column({ name: 'bitacora_id' })
  bitacora_id: string;

  @Column({ type: 'varchar' })
  evidencia_url: string;

  @Column({ type: 'tinyint', default: 0 })
  con_audio: boolean;

  @CreateDateColumn()
  creado_en: Date;

  @Column({ type: 'datetime', precision: 3, nullable: true, update: false })
  agregado_en: Date | null;

  @Column({ type: 'bigint', unsigned: true, nullable: true, update: false })
  secuencia_adicion: string | null;

  @DeleteDateColumn()
  deleted_at: Date;
}
