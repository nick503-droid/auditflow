# Actualización automática de AuditFlow PC desde el servidor LAN

La distribución se decide en el servidor: un push compila, pero **no actualiza
las PC por sí solo**. Un pull con cambios solicita exclusivamente el paquete
del commit que el servidor recibió. Android no se modifica.

## Flujo

1. GitHub Actions (`pc-release.yml`) compila en Windows cada push a `main`.
   Incluye dependencias, FFmpeg y un lanzador estable `AuditFlow.exe`.
2. El hook del servidor encola el SHA recibido por `git pull` y vuelve enseguida.
3. El publicador espera hasta una hora por el release `pc-<SHA>` exacto; no toma
   el release "latest" ni actualizaciones de otros commits.
4. Descarga y verifica ZIP + instalador. Construye el backend desde un snapshot
   de ese SHA, conservando MySQL, MinIO, storage y configuración `.env`.
   Comprueba el entrypoint en un contenedor aislado sin red ni montajes antes
   de sustituir el backend. El SHA queda incluido en la imagen, no sólo en el
   entorno del proceso. Conserva una receta privada de recuperación del backend.
5. Sólo cuando `/system/deployment` confirma el SHA publica el manifiesto LAN.
6. Las PC descargan en segundo plano. Al cerrar y volver a abrir **AuditFlow.exe**,
   el lanzador activa la nueva versión. No fuerza cierres ni detiene grabaciones.

Una caída de red o compilación fallida conserva el paquete previamente publicado.
Un pull que dice "Already up to date" no dispara `post-merge`: tampoco necesita
otro paquete. Para reintentar explícitamente: `python3 deploy/publish_pc_update.py --request`.

## Activación inicial (una vez)

### GitHub

- Subir estos cambios a `main` para que se registre el workflow. Habilitar Actions
  y permitir al workflow crear releases (`contents: write`).
- Esperar un job exitoso **Paquete Windows para actualizaciones PC**. Si falla,
  revisar el log; no se distribuye un ejecutable parcialmente construido.
- También se puede ejecutar el workflow manualmente sobre `main`.
- Los releases son prerelease deliberadamente: prepararlos no equivale a
  desplegarlos. No modificar assets de un release ya publicado.
- No se ponen EXE, ZIP, tokens ni bases de datos en Git. El workflow descarga
  FFmpeg por HTTPS y verifica el checksum publicado por su proveedor.
- La subida se prepara primero como draft; sólo se hace visible cuando todos
  los assets terminaron de subir. Un draft incompleto se puede reconstruir sin
  modificar un paquete ya publicado.

### Ubuntu (repositorio del servidor)

Prerequisitos: Python 3, Git, Docker Compose v2, DB/MinIO existentes en ejecución
y salida HTTPS a GitHub para descargar el paquete. Las PC sólo necesitan LAN.

Ejecutar como el usuario propietario del repositorio, **no con sudo**:

```bash
git pull --ff-only origin main
python3 deploy/install_pc_updates.py --install-user-timer
```

El usuario necesita acceso no interactivo a Docker; el instalador lo comprueba.
Si Docker sólo funciona con sudo, `--sudo-docker` sirve exclusivamente cuando
`sudo -n docker info` ya está autorizado. No guarda ni solicita contraseñas.
Dar acceso a Docker es un permiso administrativo: configurarlo conscientemente.

El instalador configura `core.hooksPath` sólo en este clon. Se niega a desactivar
hooks existentes. Crea `.auditflow-deploy/config.json` con permisos 0600 dentro
de un directorio 0700. Conserva configuración existente en instalaciones repetidas.

Para repositorio privado, colocar un token de lectura **Contents: read** en
`github_token` de ese archivo (o `AUDITFLOW_GITHUB_TOKEN` en el entorno del
servicio). El token se queda en Ubuntu, no se envía a PC, Android ni contenedores.
El instalador inicia la solicitud actual; si necesita token y aún no está puesto,
configurarlo y ejecutar `--request` otra vez. Un 404 también puede significar que
el repositorio es privado y falta autenticación.

Para que el timer de usuario sobreviva al cierre de sesión y al reinicio:

```bash
sudo loginctl enable-linger "$USER"
```

El timer sólo reintenta la última solicitud de pull: no ejecuta pull, no sigue
GitHub por su cuenta ni publica un commit que no esté pedido. Sin timer,
`python3 deploy/install_pc_updates.py` activa únicamente los hooks y el worker
en segundo plano; tras un reinicio se puede reanudar con `--worker`.

### PC Windows (instalación inicial)

1. Consultar `http://IP-SERVIDOR:3000/pc-updates/manifest.json`.
2. Descargar la URL relativa indicada en `installer` desde ese mismo servidor.
   También está `AuditFlow-Instalar.zip` en el release GitHub correspondiente.
3. Extraer **todos** los archivos en una carpeta permanente del usuario.
4. Abrir `AuditFlow.exe` y usarlo como acceso directo desde entonces.

No abrir el `main.exe` interno ni copiar sólo `AuditFlow.exe`. El instalador
contiene un ZIP bootstrap y sus metadatos, por lo que puede arrancar sin red.
Los ejecutables viejos no pueden adquirir un actualizador por arte de magia:
esta primera distribución es necesaria (se puede desplegar masivamente).

## Datos y configuración que se conservan

- SQLite y caché: `~/AuditFlow_Temp/`.
- Reportes/evidencias pendientes: `~/Documents/AuditFlow/`.
- Servidor configurado: `%APPDATA%/AuditFlow/config.json`.
- Un `.env` junto a `AuditFlow.exe` se carga antes de los módulos internos.
  No se empaqueta la IP ni el `.env` del desarrollador.
- Sólo los binarios viven en `%LOCALAPPDATA%/AuditFlowClient/versions/<SHA256>/`.
  Instalación por usuario, sin permisos de administrador de Windows.

El fondo consulta un manifiesto de pocos KB después de 15–45 segundos y luego
cada 12–18 minutos (aleatorio para repartir carga). El ZIP se baja sólo si hay
una compilación nueva. La ventana indica "Actualización lista al volver a abrir".
Si una descarga se corta, se descarta el temporal y se reintenta después;
la aplicación existente sigue operativa offline. No hay sincronización obligatoria
antes de actualizar: los pendientes permanecen en su DB/carpeta y se reanudan
con la siguiente versión.

## Protección y límites

- SHA-256/tamaño, metadatos internos, ZIP sin rutas externas, symlinks ni nombres
  Windows ambiguos; límites de expansión y ninguna redirección PC a otro host.
- Directorios por versión y publicación atómica: no se sobreescribe el EXE abierto.
- Arranque con confirmación de UI. Si el proceso nuevo falla **antes** de confirmar,
  se reactiva el binario anterior y se bloquea reofrecer el mismo paquete fallido.
- No se mata una aplicación que sigue viva, aunque tarde en iniciar. El rollback
  de binarios no deshace migraciones SQLite: futuras migraciones deben mantener
  compatibilidad o contar con un plan explícito de recuperación de datos.
- Los paquetes antiguos se conservan; todavía no hay limpieza automática de
  versiones. Vigilar espacio y no borrar versiones que estén en uso.
- Se rechaza downgrade automático. Para revertir código, publicarlo como otra
  compilación con número mayor, no manipular el manifiesto manualmente.
- Windows x64; un lanzador con protocolo distinto requiere una nueva distribución
  inicial. Este lanzador no se reemplaza a sí mismo mientras está abierto.
- El despliegue reinicia **sólo** el backend (puede haber una breve desconexión).
  `--no-deps` evita volver a descargar MinIO y no recrea DB/MinIO. No soluciona
  dependencias que estén detenidas. No usa `down -v` ni elimina volúmenes.
- Si falla la activación, intenta recuperar la imagen y configuración anteriores
  del backend. Verifica misma topología de montajes, puertos y red antes de
  reemplazarlo; cambios avanzados requieren recuperación manual. El rollback
  **no revierte modificaciones de esquema/datos** (MySQL `DB_SYNC=true` sigue
  existiendo). Hacer respaldos de DB/evidencias antes de desplegar.
- El estado se guarda en `.auditflow-deploy/deployment-state.json`. Un fallo de
  preflight o una recuperación exitosa bloquean reintentos automáticos del mismo
  SHA; revisar y solicitar de nuevo con `--request` conscientemente. Un corte
  mientras figura `replacing`, o `recovery_failed`, bloquea cualquier nuevo
  despliegue hasta revisar la recuperación. `--request` NO borra ese bloqueo.
- Las recetas `.auditflow-deploy/recovery/<SHA>/compose.json` contienen el entorno
  del backend: directorios 0700/archivos 0600. No compartirlas ni subirlas a Git.
  No borrar ni editar journals de recuperación sin comprobar el backend.
- `/system/deployment` devuelve la identidad incluida en la imagen. Imágenes
  antiguas o builds manuales sin SHA informan `development`; exportar un SHA al
  recrear un contenedor **no convierte código distinto en esa versión**.
- LAN controlada: SHA-256 detecta corrupción, **no autentica al editor** si un
  atacante controla el servidor/tráfico HTTP. Antes de usar redes no confiables:
  HTTPS y firma verificable de releases/ejecutables. No exponer el actualizador
  ni la API actual a Internet. Esta entrega no convierte la API en autenticada.

## Diagnóstico / detener publicaciones

```bash
tail -n 80 .auditflow-deploy/publish.log
systemctl --user status auditflow-pc-publisher.timer
journalctl --user -u auditflow-pc-publisher.service -n 80
python3 deploy/publish_pc_update.py --request
```

Desactivar `enabled` en `.auditflow-deploy/config.json` detiene nuevas
publicaciones (el manifiesto ya servido se conserva). No es necesario revertir
Git ni detener las PC. Los logs PC están en `%LOCALAPPDATA%/AuditFlowClient/updates.log`.

## Pruebas de aceptación

1. Primera instalación: abrir con red y después sin red; revisar usuario,
   configuración, borrador y evidencias anteriores.
2. Push sin pull en Ubuntu: la PC **no** recibe ese paquete.
3. Pull en Ubuntu: esperar publicación y descarga; no debe cerrarse ninguna PC.
4. Grabar vídeo/escribir durante descarga: no hay pausa, cierre ni pérdida de texto.
5. Cerrar y abrir `AuditFlow.exe`: cambia la versión del título y se conservan
   SQLite, servidor configurado y evidencias pendientes offline.
6. Cortar LAN durante descarga y luego recuperarla: el ZIP parcial nunca se activa.
7. Compilación fallida/GitHub inaccesible: sigue publicado el manifiesto anterior;
   timer/log informa pendientes y reintenta.
8. Dos pulls durante una compilación: sólo se publica el SHA solicitado vigente.
9. Varias PC: descargan independientemente y se actualizan al siguiente inicio,
   incluyendo una PC que estuvo desconectada un día.
10. Actualización de prueba que falla al arrancar antes de la UI: vuelve al binario
    anterior. Realizar en perfil de prueba, no sobre reportes de producción.

Pruebas unitarias: `python -m unittest discover -s tests -p 'test_pc*.py' -v`.
El workflow ahora exige validación Linux del backend/systemd antes del release.
`npm run build` incluye el smoke test `npm run verify:prod`, sin DB ni listener.
La prueba real de sintaxis systemd sólo se ejecuta cuando hay Linux/systemd-analyze.
Compilación manual Windows: `tools/build_pc_release.ps1 -Commit <SHA40> -Build <numero>`.
No publicar una compilación manual con un SHA que no describa realmente su código.

Para recuperar el despliegue observado el 9 de octubre, ver
[RECUPERACION_ACTUALIZADOR.md](RECUPERACION_ACTUALIZADOR.md). No seguir la guía
antigua sin preservar primero la reparación local de `backend/package.json`.

Referencias: [hooks de Git](https://git-scm.com/docs/githooks),
[PyInstaller por plataforma](https://pyinstaller.org/en/stable/operating-mode.html),
[assets de GitHub Releases](https://docs.github.com/en/rest/releases/assets?apiVersion=2022-11-28),
[FFmpeg Windows y checksums](https://www.gyan.dev/ffmpeg/builds/).
