# Gestión de usuarios y restaurantes

Respaldo de código previo: `c9beb47`. Los commits no respaldan MySQL ni evidencias.
Antes de desplegar, conservar un respaldo de la base de datos y almacenamiento.

## Alcance

- PC: Administración del Sistema → Usuarios / Restaurantes. Crear, buscar,
  editar nombres y usuario de login, filtrar activos/inactivos y activar/desactivar.
- No se borran usuarios/restaurantes, reportes, bitácoras ni archivos. DELETE
  antiguo también desactiva. Los borrados lógicos anteriores no se restauran
  automáticamente; activar/desactivar trabaja con los registros existentes no borrados.
- Usuario desactivado no puede iniciar sesión online. La propia cuenta no se
  desactiva desde la UI; el backend protege al último administrador activo,
  incluso si dos cambios llegan simultáneamente (transacción/bloqueo).
- Las acciones administrativas requieren servidor accesible y sesión ADMIN
  online en la UI. **Por decisión del propietario no se agrega JWT/guardas ni
  autorización de API.** Ocultar botones no protege la API de peticiones directas.
  Esto sigue limitado a la LAN controlada; no exponerlo a Internet.
- Android no se modifica. No se tocan los archivos de evidencias al renombrar.

## Contraseña temporal

1. ADMIN selecciona Restablecer contraseña, escribe y confirma una temporal.
2. El servidor reemplaza hash/verificador offline y marca
   `require_password_change=true`; no devuelve la contraseña ni su hash.
3. El usuario inicia sesión online con esa contraseña. Antes de entrar debe
   guardar una contraseña distinta, con confirmación. No hay recuperación de
   la contraseña anterior ni envío por correo.
4. El cambio definitivo actualiza ambos verificadores y desmarca el indicador.
   El cambio obligatorio ya existente se reutiliza; la PC muestra errores de
   validación sin confundirlos con cortes de red.
5. Mínimo 6 caracteres no vacíos; máximo 72 bytes UTF-8 por el límite de bcrypt.

No se invalidan sesiones abiertas remotamente: sigue el modelo de sesión previo.
En PC desconectadas, cambios de login/contraseña/estado se conocen al sincronizar
el directorio (actualmente una vez por minuto con conexión). El acceso offline
anterior puede persistir hasta esa sincronización o su vencimiento de 7 días.
Una contraseña temporal sincronizada no habilita acceso offline hasta que el
usuario haga el cambio obligatorio conectado. Renombrar o desactivar no borra
borradores ni archivos pendientes. Los pendientes conservan los UUID del usuario
y restaurante; los históricos siguen consultando las mismas relaciones.

## Backend y despliegue

Primero actualizar backend y después PC. No ejecutar migraciones contra una DB
de producción sin respaldo. `DB_SYNC=true` añade `restaurantes.activo` con valor
1 al arrancar. Si `DB_SYNC=false`, antes de arrancar la versión nueva:

```bash
cd backend
npm run migrate:restaurante-activo
```

La migración es idempotente y no modifica nombres/IDs. Los restaurantes existentes
no borrados quedan activos. El seeder no vuelve a crear admin/admin123 cuando
ya existen cuentas, incluyendo inactivas o borradas antiguas.

API añadida (no autenticada, como se acordó):

- GET `/usuarios/admin`, `/restaurantes/admin`: activos e inactivos, sin hashes.
- GET de catálogos existentes: sólo activos. Los detalles históricos conservan
  acceso a entidades inactivas por sus relaciones; no se aplica soft-delete.
- PATCH `/usuarios/:id`, `/restaurantes/:id`: cambios parciales y `activo: 0|1`.
- PATCH `/usuarios/:id/reset-password` con `newPassword`: contraseña temporal.
- PATCH `/usuarios/:id/password` con `newPassword`: cambio definitivo.

Un backend viejo no tiene las listas administrativas. La PC muestra que hay que
actualizarlo y no intenta escribir usando datos incompletos. Si la red cae durante
una escritura, actualizar la lista antes de repetir; no se reintentan mutaciones
automáticamente. Un fallo local de caché después de confirmar la escritura remota
no se presenta como fallo de guardado ni dispara creaciones duplicadas.

## Pruebas de aceptación

Usar cuentas/restaurantes de prueba, nunca restablecer usuarios reales para QA.

1. Crear un usuario y un restaurante. Buscarlos por nombre y login.
2. Editar nombre y login; comprobar que mantienen ID y sus registros previos.
3. Intentar repetir login de cuenta activa/inactiva: error claro, sin duplicado.
4. Desactivar empleado: desaparece del catálogo activo y no puede iniciar sesión
   online; permanece en Inactivos y conserva historial. Reactivar y repetir login.
5. Desactivar/reactivar restaurante; conserva reportes y bitácoras. Comprobar
   también un pendiente offline asociado y evidencias previas.
6. Probar último administrador: impedir desactivación/cambio a EMPLEADO; no
   ofrecer desactivar la cuenta propia en UI.
7. Restablecer a password123; login anterior falla, temporal exige cambio;
   repetir temporal como definitiva falla; una nueva distinta permite entrar.
8. Sincronizar y cortar la conexión en la PC de prueba: la definitiva funciona
   offline; la temporal pendiente exige reconexión. No borrar datos locales.
9. Cortar conexión mientras se guarda: mostrar error, conservar datos del
   formulario y verificar estado remoto antes de reintentar.
10. Navegar mientras cargan catálogos, cerrar diálogos y alternar claro/oscuro:
    no aplicar callbacks a widgets destruidos ni perder selección/filtros.

## Inspección aislada

`pc-app/venv/Scripts/python.exe -B tests/pc_appearance_fixture.py --inspect`
abre Sistema con datos ficticios. Crear/editar/activar/restablecer se simulan en
memoria, sin API, SQLite real, captura ni audio. Se pierden al cerrar la demo.
Usuario de ejemplo: `walter.demo`, contraseña inicial ficticia: `demo123`.
Restablecerla en Sistema; después elegir «Probar acceso temporal» en el selector
inferior para recorrer manualmente el cambio obligatorio. Volver a Sistema desde
ese selector recupera el administrador ficticio. Esto no prueba red entre PCs.
