import { MoreThanOrEqual, Repository } from 'typeorm';

/**
 * Conjunto de caracteres sin ambigüedades visuales:
 *   - sin 'I' (confunde con '1' o 'l')
 *   - sin 'O' (confunde con '0')
 *   - sin '0' y '1' (confunden con 'O' e 'I'/'l')
 */
const CARACTERES_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789' as const;

/** Número de caracteres del código generado. */
const LONGITUD_CODIGO = 6 as const;

/** Ventana de unicidad por defecto (días). */
const DIAS_VIGENCIA_DEFAULT = 5 as const;

/** Número máximo de reintentos antes de lanzar un error. */
const MAX_INTENTOS = 10 as const;

// ---------------------------------------------------------------------------

/**
 * Genera un código aleatorio de `LONGITUD_CODIGO` caracteres tomados de
 * `CARACTERES_CODIGO`. No realiza ninguna consulta a la base de datos.
 *
 * @returns Código candidato en mayúsculas (ej. "A3KM7T").
 */
export function generarCodigoAleatorio(): string {
  let resultado = '';
  for (let i = 0; i < LONGITUD_CODIGO; i++) {
    const indice = Math.floor(Math.random() * CARACTERES_CODIGO.length);
    resultado += CARACTERES_CODIGO[indice];
  }
  return resultado;
}

// ---------------------------------------------------------------------------

/**
 * Opciones para {@link generarCodigoUnico}.
 */
export interface GenerarCodigoOptions {
  /**
   * Campo de la entidad donde se almacena el código
   * (debe ser una clave de `TEntity`).
   */
  campoCodigo: string;

  /**
   * Campo de fecha de la entidad usado para calcular la ventana de unicidad.
   * Si no se provee, la verificación de colisión ignora la fecha (busca
   * en todos los registros).
   */
  campoFecha?: string;

  /**
   * Días hacia atrás en los que se considera "activo" un código.
   * Dos códigos generados con más de `diasVigencia` días de diferencia
   * pueden coincidir sin causar conflicto en la app.
   * @default 5
   */
  diasVigencia?: number;
}

// ---------------------------------------------------------------------------

/**
 * Genera un código de vinculación único de 6 caracteres para cualquier
 * entidad que use este mecanismo (Bitácoras, Reportes, etc.).
 *
 * El algoritmo reintenta hasta {@link MAX_INTENTOS} veces en caso de
 * colisión. La probabilidad de colisión con ≤1 000 códigos activos es
 * menor al 0.001 %, por lo que el límite de 10 intentos es más que
 * suficiente para producción.
 *
 * @param repo           - Repositorio TypeORM de la entidad objetivo.
 * @param options        - Configuración de campo y ventana temporal.
 * @returns              Promise que resuelve con el código único generado.
 * @throws               Error si no se logra unicidad tras MAX_INTENTOS.
 *
 * @example
 * // En BitacorasService:
 * const codigo = await generarCodigoUnico(this.bitacorasRepo, {
 *   campoCodigo: 'codigo',
 *   campoFecha: 'fecha',
 *   diasVigencia: 5,
 * });
 *
 * @example
 * // En ReportesService:
 * const codigo = await generarCodigoUnico(this.reportesRepo, {
 *   campoCodigo: 'codigo',
 *   campoFecha: 'fecha_jornada',
 * });
 */
export async function generarCodigoUnico<TEntity extends object>(
  repo: Repository<TEntity>,
  options: GenerarCodigoOptions,
): Promise<string> {
  const { campoCodigo, campoFecha, diasVigencia = DIAS_VIGENCIA_DEFAULT } = options;

  const fechaLimite = new Date();
  fechaLimite.setDate(fechaLimite.getDate() - diasVigencia);

  for (let intento = 0; intento < MAX_INTENTOS; intento++) {
    const candidato = generarCodigoAleatorio();

    // Construir el objeto `where` dinámicamente.
    // El cast a `any` es el único punto de escape de tipado estricto en esta
    // función genérica; es intencionado y está contenido aquí para no
    // propagar el `any` hacia los servicios consumidores.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const where: Record<string, any> = {
      [campoCodigo]: candidato,
    };

    if (campoFecha) {
      where[campoFecha] = MoreThanOrEqual(fechaLimite);
    }

    const existente = await repo.findOne({ where });

    if (!existente) {
      return candidato;
    }
  }

  throw new Error(
    `[CodeGenerator] No se pudo generar un código único en ${MAX_INTENTOS} intentos. ` +
      'Verifica que el espacio de códigos no esté saturado.',
  );
}
