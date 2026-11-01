import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  ManyToOne,
  JoinColumn,
  DeleteDateColumn,
  Index,
} from 'typeorm';
import { Reporte } from '../../reportes/entities/reporte.entity';

@Entity('evidencias_reporte')
@Index('uq_ev_reporte_adicion', ['reporte_id', 'secuencia_adicion'], { unique: true })
export class EvidenciaReporte {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  // Lado "muchos" de la relación: aquí SÍ existe la columna FK real
  @ManyToOne(() => Reporte, (reporte) => reporte.evidencias)
  @JoinColumn({ name: 'reporte_id' })
  reporte: Reporte;

  @Column({ name: 'reporte_id' })
  reporte_id: string;

  @Column({ type: 'varchar' })
  evidencia_url: string;

  @Column({ type: 'tinyint', default: 0 })
  con_audio: boolean;

  @Column({ type: 'int', default: 0 })
  orden_reproduccion: number;

  @Column({ type: 'datetime', precision: 3, nullable: true, update: false })
  agregado_en: Date | null;

  @Column({ type: 'bigint', unsigned: true, nullable: true, update: false })
  secuencia_adicion: string | null;

  @DeleteDateColumn()
  deleted_at: Date;
}
