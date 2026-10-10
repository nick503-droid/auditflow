# Correcciones del actualizador - 9 de octubre de 2026

## Confirmado y corregido en desarrollo

- `npm run build` produce `dist/src/main.js`, porque el build incluye `src/` y
  las migraciones TypeScript de `scripts/`. `start:prod` apuntaba a `dist/main`.
  Ahora usa el archivo correcto y cada build verifica el bootstrap compilado
  con NestFactory simulado: no abre puertos, no conecta DB ni ejecuta seeds.
- WorkingDirectory de systemd no admite el quoting de ExecStart. Ahora se
  escribe la ruta absoluta literal, con porcentajes escapados y control de
  caracteres que podrían inyectar directivas. ExecStart conserva quoting y
  desactiva expansión de variables de shell mediante su prefijo `:`.
  El instalador valida ambas unidades antes de reemplazar las existentes.
- La imagen incluye `deployment.json` y su etiqueta de SHA durante el build
  del snapshot Git. La API usa ese archivo y no confía en un SHA arbitrario de
  runtime. Builds manuales sin identidad e imágenes antiguas siguen siendo
  `development`; no falsificar ese resultado.
- Antes de activar, se inspecciona el backend actual, conserva su imagen,
  entorno, comando, montajes y red en una receta privada. Se construye la
  candidata sin parar el backend y se comprueba su entrypoint sin DB/red.
  Si falla después de activar, se intenta recuperar el backend anterior.
- Un fallo determinista no entra en un ciclo de reinicios por timer. El journal
  conserva la incidencia, y el manifiesto PC anterior no se sustituye. Una
  recuperación interrumpida o fallida requiere intervención, no otro pull.
- Se mantienen el bloqueo por cambios staged/no staged, checksum/tamaño,
  verificación de SHA, publicación atómica y activación PC al siguiente inicio.
  Android, credenciales y directorios de datos no se modificaron.

## Lo que el registro NO demuestra

- El backend responde `development` y el timer está enabled pero inactive.
  Eso no significa que la publicación haya finalizado. El oneshot inactive al
  terminar sí puede ser normal; el timer inactive no se considera operativo.
- El cambio local de package.json explica el bloqueo de cambios, pero la
  secuencia exacta que recreó el contenedor sin SHA sigue siendo una hipótesis.
- Tener un archivo worker.lock no prueba que esté retenido: flock depende del
  proceso, no de la existencia del archivo. No borrarlo como solución.
- El aviso spice-vdagent del PDF pertenece a otra unidad, no a AuditFlow.

## Pruebas locales seguras

Desde la raíz:

```powershell
python -m unittest discover -s tests -p "test_pc*.py" -v
cd backend
npm run build
npm test -- --runInBand --runTestsByPath src/modules/system/system.controller.spec.ts src/modules/bitacoras/bitacoras.service.spec.ts
```

En Linux de pruebas, los tests ejecutan systemd-analyze verify sin instalar ni
iniciar unidades. En Windows esa prueba se omite. Docker/GitHub del publicador
se simulan; una prueba aprobada no garantiza que Docker en producción funcione.

Las mismas verificaciones se añaden al workflow antes de publicar paquetes.
El SHA del paquete sigue correspondiendo al release `pc-<SHA completo>`.

Resultados en desarrollo Windows, 9 de octubre de 2026:

- Python: 41 pruebas descubiertas; 40 aprobadas y 1 omitida (systemd real).
- Jest: 11 pruebas aprobadas en system/bitácoras, 2 suites.
- Build NestJS y smoke test del entrypoint: aprobados; ubicación confirmada
  `backend/dist/src/main.js`. Esto no es una conexión real con MySQL.
- `docker compose config --quiet`: aprobado, con la advertencia preexistente
  `version is obsolete`. El daemon Docker local no estaba activo.
- `git diff --check`: aprobado. No se ejecutaron commits, push ni despliegues.

## Archivos modificados y finalidad

| Archivo | Cambio |
| --- | --- |
| backend/package.json | Arranque correcto y verificación postbuild |
| backend/scripts/verify-production.cjs | Smoke del entrypoint e identidad sin DB/red |
| backend/Dockerfile | Identidad inmutable incluida al construir la imagen |
| backend/.dockerignore | No copiar artefactos locales, datos ni .env al build |
| backend/src/modules/system/system.controller.ts | Responder SHA de la imagen, no del entorno |
| backend/src/modules/system/system.controller.spec.ts | Regresiones de identidad y metadatos inválidos |
| docker-compose.yml | Transmitir el SHA como argumento de build |
| deploy/install_pc_updates.py | Generar y validar unidades correctas/idempotentes |
| deploy/publish_pc_update.py | Preflight, receta/recuperación y reintentos protegidos |
| tests/test_pc_updates.py | Preservar manifiestos y bloqueos; verificar publicación final |
| tests/test_pc_deploy.py | Regresiones systemd, captura, activación, recuperación y concurrencia |
| .github/workflows/pc-release.yml | Exigir validación Linux antes de generar/publicar release Windows |
| .gitignore | No versionar metadatos locales de build |
| deploy/README.md | Actualizar funcionamiento, garantías y límites |
| deploy/RECUPERACION_ACTUALIZADOR.md | Diagnóstico, resultados y procedimiento de aceptación |

## Aplicación posterior en Ubuntu (NO ejecutada por el asistente)

Sólo después de revisar, autorizar y publicar los cambios desde Windows, y
confirmar el job de GitHub Actions para el nuevo commit. No construir ni
distribuir los paquetes locales de prueba como versiones reales.

1. Tener respaldo probado de MySQL/evidencias/configuración. El patch de
   package.json no es respaldo de datos. Verificar que DB/MinIO y API estén Up.
2. Parar el timer durante esta intervención controlada y comprobar que no hay
   un worker activo. Si existe, esperar que termine; no interrumpir una fase
   `replacing`. No borrar worker.lock ni detener Docker/DB/MinIO.
3. Preservar el cambio local de package.json (incluye staging) antes del pull.
   No ejecutar staging/limpieza/stash globales: storage_data es dato real.

```bash
cd ~/servidor/auditflow
docker compose ps
git status --short
git diff HEAD -- backend/package.json
systemctl --user stop auditflow-pc-publisher.timer
systemctl --user status auditflow-pc-publisher.service --no-pager
pgrep -af '[p]ublish_pc_update.py'
```

`pgrep` sin resultados sale con código 1; no significa una avería. También hay
workers que se lanzan desde los hooks y no aparecen como servicio systemd.
Si hay worker activo, detener aquí el procedimiento y revisar su fase/logs.

Respaldo NUEVO sin sobrescribir uno anterior (`noclobber`):

```bash
(set -C; git diff HEAD -- backend/package.json > "$HOME/auditflow-package-respaldo-2026-10-09.patch")
```

Si existe, conservarlo y elegir otro nombre. No continuar si falló el respaldo
o si hay cambios locales adicionales que aún no se han revisado.

```bash
git stash push -m "Respaldo correccion backend Ubuntu" -- backend/package.json
git pull --ff-only origin main
python3 deploy/install_pc_updates.py --install-user-timer
```

El instalador activa el timer y encola la publicación; ese paso puede desplegar
el backend. Ejecutarlo sólo en la ventana autorizada. No hacer stash pop: el
código nuevo ya incluye la reparación. Conservar el stash para recuperación.
El hook del pull también puede encolar un worker: DB/MinIO y respaldo deben
estar listos ANTES del pull. Para impedirlo temporalmente, desactivar `enabled`
en la configuración privada, conservando los demás campos, antes de ese paso;
el instalador vuelve a habilitarlo. No compartir tokens ni config.json.

`enable-linger` se había ejecutado antes; comprobarlo, no repetir por rutina:

```bash
loginctl show-user "$USER" -p Linger
systemd-analyze --user verify ~/.config/systemd/user/auditflow-pc-publisher.service ~/.config/systemd/user/auditflow-pc-publisher.timer
systemctl --user status auditflow-pc-publisher.timer --no-pager
tail -n 80 .auditflow-deploy/publish.log
git rev-parse HEAD
```

Verificar: timer active (waiting), mensaje PUBLICADO reciente y respuestas HTTP
200 cuyo SHA coincida con HEAD. No exportar manualmente el SHA para maquillar
la comprobación. No ejecutar `docker compose up --build` por fuera del flujo
controlado, porque se construye otro código/configuración y puede cambiar la
identidad. `--no-deps` conserva DB/MinIO existentes, no arranca dependencias caídas.

Consulta sin curl:

```bash
python3 - <<'PY'
import json, subprocess, urllib.request
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
for route in ('/system/deployment', '/pc-updates/manifest.json'):
    with urllib.request.urlopen('http://127.0.0.1:3000' + route, timeout=5) as response:
        data = json.load(response)
        print(route, response.status, data)
        assert data.get('commit') == head, 'No coincide con HEAD'
        if route.endswith('manifest.json'):
            assert data.get('installer'), 'Falta instalador'
PY
```

Si hay preflight_failed/recovered: revisar causa antes de `--request` (éste
autoriza un nuevo intento de ese SHA). Si hay replacing/recovery_failed:
verificar el contenedor y la receta privada con un operador; no borrar el
journal para forzar otra actualización. No reiniciar a ciegas el publicador.

## Prueba Windows posterior

1. Descargar la ruta installer del manifiesto desde la IP LAN REAL del servidor
   (localhost sólo sirve en Ubuntu). Extraer TODO el ZIP y abrir AuditFlow.exe.
2. Usar un perfil/PC de prueba con borrador y evidencia offline existentes.
   Confirmar usuario, servidor configurado, texto y archivos tras iniciar.
3. Mantener otra versión abierta mientras se publica un NUEVO commit. Verificar
   que descarga en fondo sin cerrar ventana, interrumpir grabación ni perder texto.
4. Cerrar y abrir AuditFlow.exe. Confirmar versión/commit y conservación de SQLite,
   configuración y evidencias pendientes; comprobar su sincronización posterior.
5. Cortar LAN durante descarga: no activar ZIP parcial; recuperar y reintentar.
6. Ensayar fallo/recuperación en entorno separado, nunca contra DB de producción.

## Límites y riesgos pendientes

- La recuperación de Docker y la sintaxis real systemd deben validarse en Linux
  aislado y después en una intervención autorizada. No se ha accedido a Ubuntu.
- Recuperar binarios no deshace migraciones MySQL/SQLite. DB_SYNC=true puede
  modificar esquemas al iniciar; respaldos y compatibilidad siguen siendo necesarios.
- La recuperación automática soporta la topología Compose actual. Si cambian
  montajes, puertos, redes u opciones avanzadas, se detiene antes de reemplazar.
- Las recetas incluyen variables privadas y sólo se guardan en Ubuntu con
  permisos restrictivos. No publicarlas. El journal no es un respaldo de DB.
- El workflow no se ejecutó remotamente ni se crearon releases en esta revisión.
- Sin daemon Docker disponible, las pruebas de reemplazo/recuperación fueron
  simuladas. No se afirma funcionamiento end-to-end en la empresa.
- Mantener LAN controlada: no se resolvió autenticación de API ni firma/HTTPS
  de actualizaciones. Las vulnerabilidades npm requieren revisión independiente.

Referencias de sintaxis: [parser oficial WorkingDirectory](https://github.com/systemd/systemd/blob/main/src/core/load-fragment.c),
[ExecStart y expansión](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml),
[recreación Compose y montajes](https://docs.docker.com/reference/cli/docker/compose/up/).
