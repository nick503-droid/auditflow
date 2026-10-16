# Diseño PC: iconos y apariencia claro/oscuro

## Alcance

Cambio exclusivamente visual de la aplicación PC. No modifica endpoints,
SQLite, sincronización, grabación, subida de evidencias, Android ni el protocolo
de actualización. Los cambios de la configuración CI sólo añaden la dependencia
necesaria para ejecutar las pruebas visuales aisladas.

El respaldo de fuentes previo al diseño es el commit `96f3256`; el ZIP manual
estable y sus hashes están documentados en `ESTADO_ESTABLE_PRE_DISENO.md`.
No se sobrescribió ese ZIP ni se recompiló el ejecutable estable.

## Uso

- Selector **Modo oscuro / Modo claro** en el borde inferior, disponible en todos
  los módulos. Atajo: **Ctrl+Shift+L**.
- Cambia los widgets existentes, sin navegar ni reconstruir el editor. Conserva
  texto, cursor, evidencias seleccionadas y estado de los módulos.
- La preferencia queda sólo en `%APPDATA%/AuditFlow/appearance.json` en Windows
  (o `~/.config/AuditFlow/appearance.json` sin APPDATA). No cambia `config.json`,
  usuarios ni ajustes del servidor. Sin preferencia previa se conserva modo claro.
- El calendario y las ventanas CTk propias siguen el tema. Los diálogos nativos
  del sistema (archivos y mensajes de Windows) dependen de su tema de Windows.

## Paleta e iconos

Referencia: HTML de paleta ergonómica suministrado por el usuario. Fondo oscuro
`#121214`, tarjetas `#1E1E24`, elevación `#282830`, contornos `#32323D`, texto
`#E4E4E7` y acentos índigo, celeste, menta, ámbar y coral. Se ajustó el índigo
de botones y el texto secundario cuando era necesario para contraste AA real;
no se asumen válidas las afirmaciones de contraste o de salud visual del HTML.

Los iconos son trazos propios RGBA transparentes con variantes claro/oscuro y
caché limitada. No necesitan fuentes emoji, Internet ni nuevos binarios. Las
fotografías y miniaturas de evidencias no se recolorean. Los iconos compartidos
retiran los callbacks de widgets destruidos para no retener tarjetas en memoria.

`ui/auditflow_theme.json` se incluye mediante la regla ya existente de `main.spec`.
El cambio no altera cómo se empaqueta FFmpeg ni activa el actualizador en la
distribución manual. Para ver el nuevo diseño será necesario compilar otra
versión; conservar el ZIP estable en una ubicación aparte antes de hacerlo.

## Verificación

```powershell
.\pc-app\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_pc*.py'
.\pc-app\venv\Scripts\python.exe -B tests/pc_appearance_fixture.py --smoke
```

Las fixtures construyen las vistas reales con API, DB, audio y miniaturas
simulados. No consultan la red ni los datos de auditorías. Las pruebas cubren
contraste, transparencia, preferencia local, cambios in-place, callbacks de
iconos y las vistas de inicio, editor, bitácoras, administración y evidencias.
Con tkcalendar instalado también comprueban el calendario en ambos modos.

Resultado local en Windows con el entorno virtual de la compilación manual:
82 pruebas ejecutadas, 81 aprobadas y una omitida por requerir Linux. La
inspección de contraste incluye colores normales y hover de labels/botones
en las vistas construidas. El ZIP y el ejecutable estable conservan los SHA-256
del punto de respaldo.

Para inspección manual con datos ficticios se puede ejecutar esa fixture sin
`--smoke`. No es el programa de producción. En esta sesión la captura mediante
la herramienta de control de Windows falló por timeout: no se da por validada
una captura visual integral de esas ventanas. Sí se inspeccionó la lámina de
iconos y se verificó la construcción real de los widgets con pruebas aisladas.

Prueba de aceptación en una PC: cambiar tema con un reporte abierto y texto
sin enviar, seleccionar evidencias, abrir el visor, revisar menús/calendario y
reiniciar para confirmar la preferencia. No debe perderse texto ni selección.

## Revertir sólo el diseño

Usar `git revert SHA_DEL_COMMIT_VISUAL` después de comprobar que se trata del
commit de diseño posterior a `96f3256`. Esto conserva el historial y los datos.
No ejecutar `git reset --hard`, borrar bases de datos ni sustituir carpetas de
evidencias. La preferencia de apariencia queda inerte con el código anterior.
