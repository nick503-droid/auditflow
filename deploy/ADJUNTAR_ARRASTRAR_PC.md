# Adjuntar evidencia: buscar o arrastrar y soltar

Respaldo previo: `1ac18f8`.

## Uso

En **Reportes** y **Bitácoras**, pulsa Adjuntar archivo/evidencia:

1. Usa **Buscar archivos** o arrastra uno o varios archivos del Explorador a la zona indicada.
2. Revisa la lista. Puedes añadir más archivos o pulsar **Quitar** sin borrar el original.
3. Pulsa **Adjuntar** (también Ctrl+Enter) para confirmar. Cancelar/Escape no adjunta nada.

Los archivos se copian, no se mueven. Se conserva el orden en que se incorporan a la lista y se utiliza la cola local existente para trabajar sin conexión. Los reportes guardan cada adjunto en una ruta propia para no sobrescribir dos archivos que tengan el mismo nombre.

La selección de varios archivos de una sola vez respeta el orden que entregue el Explorador/selector; si necesitas un orden concreto, añádelos en ese orden a la lista. El sistema no puede reconstruir el orden de clics internos del Explorador.

Se aceptan archivos regulares, igual que con la opción anterior Todos los archivos. Las carpetas, rutas no disponibles y archivos vacíos se notifican en el cuadro. No se abre ni ejecuta el contenido de los adjuntos para seleccionarlos. La vista previa sigue dependiendo de los formatos ya soportados.

Si falla la carga del soporte nativo de arrastre, Buscar archivos sigue disponible y el cuadro lo indica. No se modifican grabación, audio, permisos del servidor ni las frecuencias de polling.

## Compilar

Desde `pc-app`, usando el entorno de compilación habitual:

```powershell
.\venv\Scripts\python.exe -m pip install tkinterdnd2==0.6.4
.\venv\Scripts\python.exe -m PyInstaller --clean --noconfirm main.spec
```

`main.spec` incluye el paquete TkDnD, sus archivos Tcl/DLL y los metadatos/licencia, además del FFmpeg que ya se empaquetaba. `main.exe --self-test` ahora verifica también la carga de tkdnd. No copiar DLLs a mano ni ejecutar una instalación incompleta.

Integración sobre la raíz CTk existente y tratamiento de las rutas como listas Tcl conforme a la [documentación de tkinterdnd2](https://pypi.org/project/tkinterdnd2/0.6.4/). No se crea una segunda raíz Tk ni otro mainloop de la aplicación.

## Prueba manual

Repetir en ambos módulos, en claro y oscuro:

- Buscar dos archivos y cancelar: ninguna evidencia nueva.
- Arrastrar varias imágenes/videos; probar nombres con espacios y acentos.
- Soltar repetido el mismo archivo: aparece una sola vez en la selección.
- Quitar un archivo de la lista y confirmar los demás.
- Soltar una carpeta o archivo vacío: aviso sin cierre del sistema.
- Adjuntar archivos del mismo nombre, ubicados en carpetas diferentes: ambos conservan su contenido y los originales permanecen intactos.
- Sin conexión, confirmar A/B/C; reconectar y comprobar su orden después de la subida y de reabrir.

Las pruebas automatizadas usan archivos temporales y eventos Drop sintetizados con listas Tcl, cargan TkDnD real y prueban los colores y callbacks. No equivalen a haber realizado un arrastre físico desde el Explorador en cada equipo: comprobar también ese gesto con el nuevo ejecutable.
