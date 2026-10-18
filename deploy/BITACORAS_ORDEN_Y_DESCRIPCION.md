# Bitácoras: orden de creación y descripción flexible

Respaldo local previo al cambio: `2f1c383` (estado de código de `4d708e1`).
Este commit es un respaldo de código, no de la base de datos ni las evidencias.

## Comportamiento

- Las bitácoras de un día se muestran de la más antigua a la más nueva según
  `created_at`, asignado por MySQL al insertar. `hora` sigue siendo texto libre
  del evento (por ejemplo, hora de California); no determina la posición.
- Los empates de creación se resuelven siempre por `id`. La precisión es de
  milisegundos, igual que las fechas que NestJS transmite en JSON.
- Editar texto, hora, urgencia o evidencias cambia `updated_at`, no `created_at`.
- La PC coloca las tarjetas existentes sin reconstruir los controles ni
  cambiar los índices usados por sus callbacks. Una llegada tardía puede
  insertarse en su posición correcta conservando texto, selección y foco.
- Las filas aún offline quedan al final. SQLite las envía por su ID local
  ascendente, no por el reloj ni por la última edición. Su orden global
  definitivo es el de creación **al recibirse en el servidor**, no el instante
  físico de escritura offline en PCs cuyos relojes no son confiables.
- El cursor de polling usa `updated_at` recibido del servidor y solapa 1 ms.
  Una diferencia de reloj de la PC no debe saltarse cambios. Los deltas
  repetidos sin modificaciones no reconstruyen tarjetas. No se aumentó la
  frecuencia de polling (5 segundos).
- La descripción crece y se reduce por los píxeles reales del texto envuelto,
  incluidos saltos manuales, pegado y actualizaciones remotas. Se recalcula al
  cambiar el ancho del editor o la escala de pantalla. Sin scroll interno,
  sin altura máxima artificial y sin `update_idletasks()` recursivo. Se suprime
  el sondeo periódico de barras de desplazamiento de cada descripción; el
  ajuste se programa por eventos y se agrupa durante la edición.
- Enter conserva el flujo hacia la siguiente fila; Shift+Enter inserta un
  salto de línea. Ambos temas usan la misma lógica.

## Actualización del servidor

Hacer primero una copia de seguridad de MySQL. No borrar volúmenes Docker.

La configuración actual del repositorio tiene `DB_SYNC=true`: al arrancar
el backend nuevo, TypeORM añade `created_at` y el índice
`idx_bitacoras_fecha_creacion`. No requiere cambios de Android.

Para instalaciones con `DB_SYNC=false`, ejecutar la migración **antes de
arrancar el backend nuevo**, con las variables de conexión de esa instalación:

```sh
cd backend
npm run migrate:bitacora-created-at
```

La migración comprueba si existen la columna y el índice antes de crearlos.
No borra bitácoras ni modifica archivos de evidencias. No ejecutarla contra
otra base de datos: comprobar `DB_HOST` y `DB_NAME` de antemano.

### Registros anteriores

La entidad anterior no tenía `created_at`. Si la base tampoco lo tenía,
MySQL asigna a las filas antiguas el instante de incorporación de la columna.
Entre ellas se conserva un orden estable por UUID, **no una cronología
histórica reconstruida**. `updated_at` no puede recuperar ese dato porque
se ha modificado con cada edición. Si una instalación ya conserva un
`created_at` real, la migración manual no lo sobrescribe.

Los registros nuevos sí disponen de una creación real del servidor. Para ver
los cambios de interfaz, generar y distribuir el nuevo ejecutable de Windows;
actualizar únicamente el backend no modifica las descripciones del exe viejo.

## Pruebas de aceptación en dos PCs

1. Crear tres bitácoras con horas de evento deliberadamente desordenadas
   (`1:35 pm`, `8:55 AM`, `10:06 AM`). Las nuevas deben quedar en el orden en
   que se crearon en el servidor; repetir tras salir y volver a entrar.
2. Editar la primera y adjuntarle evidencia. No debe cambiar de posición.
3. Crear filas en ambas PCs. Deben coincidir en el orden por creación, sin
   importar la zona horaria de Windows. No modificar el reloj del servidor.
4. Pegar varias líneas y texto largo sin saltos. Comprobar la primera y la
   última línea, ensanchar/estrechar la ventana y abrir/cerrar el panel de
   evidencias. El texto debe seguir completo y editable.
5. Repetir en claro y oscuro, y con escala de Windows 125 %, 150 % o 200 %.
6. Mientras una PC escribe, crear otra bitácora en la segunda: no debe perder
   el foco ni editarse otra fila. Verificar también que un alta y su primer
   delta no creen dos tarjetas del mismo `client_id`.
7. Crear pendientes offline, editar la primera después de la segunda y
   reconectar. La cola se envía por secuencia local; no cambia por esa edición.
