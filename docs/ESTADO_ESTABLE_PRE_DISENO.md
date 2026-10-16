# Punto de respaldo antes del cambio visual de PC

Fecha: 2026-10-16. El usuario confirmó que la distribución manual funciona.

El código funcional de este punto corresponde a
`12e04754c4d78fce5c678ac2ae92d201da7d792c`. El commit que incorpora este
documento es el punto de control inmediatamente anterior al cambio visual.
No modifica la aplicación, el backend, Android ni el actualizador.

## Paquete manual conservado

Los siguientes archivos locales se conservan sin recompilar ni sobrescribir.
Son artefactos de distribución, no fuentes que deban añadirse al repositorio:

| Archivo | SHA-256 |
| --- | --- |
| `pc-app/dist/AuditFlow_PC_App.zip` | `1c825099d3da1a74e35591cb3ac2866eeb4370f82ae50665f2b4765f69cdf6ad` |
| `pc-app/dist/main/main.exe` | `be3c6b3fca7d12a5a453d33fa9d4af4ee8e214e710db7b7d1a2dab3d9c11a924` |
| `pc-app/dist/main/_internal/ffmpeg.exe` | `57c56e369d5b4873b4d93fc1a1d833cb7cd8bc9325c14b05c34ce60b22842d8a` |

El `version.json` local identifica la compilación manual como
`4-12e04754c4d7`. Esta etiqueta no activa por sí sola la autoactualización.

También se conservan las modificaciones preexistentes de `pc-app/build/main/`
y los `.pyc` generados por el usuario, así como `output/` y `tmp/`. No se
mezclan con el cambio visual ni se incluyen bases de datos o configuración privada.

## Comprobación previa

`py -3.10 -B -m unittest discover -s tests -p 'test_pc*.py'`

Resultado: 68 pruebas ejecutadas; 67 aprobadas y una omitida porque requiere
Linux. Esto no sustituye las pruebas del usuario en las PCs de la empresa.

## Recuperación

El diseño se guardará en un commit posterior separado. Para deshacerlo se
puede revertir únicamente ese commit visual, preservando el historial y los
datos. No usar `git reset --hard` ni borrar carpetas de datos. El ZIP manual
original seguirá disponible en la ruta indicada, salvo que el usuario lo
reemplace posteriormente.
