# Orden de incorporación de evidencias nuevas

Respaldo previo: `13d2079`. No se cambia el audio ni se reconstruye la cronología histórica.

## Funcionamiento

- Reportes y Bitácoras nuevos guardan `agregado_en`, en UTC con milisegundos, al registrar cada archivo local. La cola conserva esa fecha durante los reintentos y la envía al vincular el archivo.
- El reloj de incorporaciones de la PC se conserva en SQLite aunque se vacíe la cola o se reinicie la aplicación. Dos altas en el mismo milisegundo reciben marcas consecutivas; no se usa COUNT de pendientes.
- El servidor guarda la fecha y una `secuencia_adicion` numérica por reporte/bitácora. Si coinciden las fechas, desempata por esa secuencia, no por el UUID. Un bloqueo transaccional por padre protege las altas simultáneas; evidencia y notificación al padre se confirman juntas. No hay nuevas consultas HTTP periódicas ni una reconstrucción completa de tarjetas.
- Los clientes móviles nuevos envían la fecha antes de subir el archivo. Los APK/clientes anteriores siguen funcionando: si no envían fecha se usa la recepción en el backend, que no puede conocer el momento previo de selección.
- Editores y Administración usan el mismo criterio. En la PC, pendientes y nube se muestran en una lista cronológica; la etiqueta continúa identificando si el archivo sigue pendiente.
- Las filas antiguas mantienen los campos nuevos en NULL y se muestran con un criterio estable de compatibilidad, antes de las nuevas. No se inventan fechas históricas.

La zona horaria de California/El Salvador no cambia el orden UTC. Entre equipos distintos, la precisión de la hora original depende de que sus relojes estén correctamente configurados: no es posible reconstruir la hora real de una incorporación offline si el reloj de esa PC estaba equivocado. En empates exactos de distintos equipos, la secuencia representa el orden de registro en el servidor.

## Despliegue

Se requieren **backend y ejecutable PC nuevos**. Este cambio de código por sí solo no modifica ZIPs/APKs ya construidos ni publica una versión.

1. Respaldar la base de datos y conservar el ejecutable anterior.
2. Actualizar/reconstruir el backend antes de usar la PC nueva. El Compose del repositorio tiene `DB_SYNC=true`, por lo que TypeORM añade las columnas e índices al iniciar.
3. Si la instalación usa `DB_SYNC=false`, ejecutar la migración idempotente con la configuración de su base de datos **antes de arrancar el backend nuevo**:

   ```bash
   cd backend
   npm run migrate:evidence-order
   ```

   En una imagen ya construida también existe `node dist/scripts/migrate-evidence-order.js`; usa las variables DB_* del contenedor. No ejecutar simultáneamente la migración y el sincronizador de esquema.
4. Distribuir el nuevo ejecutable PC. Para conservar la selección original del teléfono antes de una subida lenta, reconstruir/distribuir también el APK; un APK anterior usa la recepción del servidor como referencia.
5. Para volver a código anterior, conservar las columnas nuevas y el reloj SQLite: son aditivos. No borrar evidencias, archivos ni datos locales pendientes.

## Pruebas en la empresa

Repetir en Reportes y Bitácoras:

1. Adjuntar A, esperar tres segundos, adjuntar B y después C. Comprobar A → B → C antes y después de la subida.
2. Añadir A offline, añadir B/C, reconectar y dejar terminar la cola. Verificar el mismo orden al cerrar y reabrir y en Administración.
3. Dejar A pendiente en una PC, subir B desde otro dispositivo con hora correcta y después reconectar la primera PC: A debe conservar su fecha original.
4. Subir A, esperar que desaparezca de pendientes, agregar B. B no debe adelantar a A aunque la cola haya quedado vacía.
5. Eliminar B de A/B/C, agregar D: A → C → D.
6. Adjuntar varios archivos rápidamente y recibir evidencias desde móvil. Confirmar que las tarjetas no parpadean ni pierden selecciones de descarga al recibir otra evidencia.

Las pruebas automatizadas usan SQLite temporal, metadatos/SQL MySQL sin conexión y repositorios simulados con contrato de bloqueo/rollback. No modifican la base del usuario ni sustituyen la prueba de concurrencia sobre el servidor real.
