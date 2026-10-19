# Credenciales locales (fuera de git, fuera del alcance de las IAs)

Este directorio guarda **lo confidencial**. Nada de lo que hay aquí se sube al
repositorio ni lo pueden leer los asistentes de IA:

- `.gitignore` de la raíz ignora todo `.secrets/` salvo este README y los `*.ejemplo`.
- `.secrets/.gitignore` lo vuelve a ignorar desde adentro, por si el de la raíz cambia.
- `.claude/settings.json` declara `permissions.deny` sobre `.secrets/**`, así que
  Claude Code no puede abrir, editar ni `cat`ear estos archivos.

`config.py` sólo conoce las **rutas** de estos archivos. Nunca su contenido.

---

## Qué hay que poner aquí

### 1. `service_account.json` — la llave de la cuenta de servicio de Google

Es el JSON que descargas de Google Cloud. Pasos, una sola vez:

1. Entra a <https://console.cloud.google.com/> y elige (o crea) un proyecto.
2. **APIs y servicios → Biblioteca → Google Drive API → Habilitar**.
3. **APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio**.
   Ponle un nombre (p. ej. `etl-desaparecidos`) y créala. No necesita ningún rol
   de IAM: los permisos sobre los archivos se los da Drive, no Google Cloud.
4. Abre la cuenta de servicio → pestaña **Claves** → **Agregar clave → Crear clave
   nueva → JSON**. Se descarga un archivo.
5. Muévelo aquí con ese nombre exacto:

   ```bash
   mv ~/Descargas/<lo-que-sea>.json .secrets/service_account.json
   chmod 600 .secrets/service_account.json
   ```

6. Abre el JSON y copia el valor de `client_email`. Se ve así:
   `etl-desaparecidos@mi-proyecto.iam.gserviceaccount.com`.

### 2. Compartir la carpeta de Drive con esa cuenta

La cuenta de servicio es un usuario aparte: **no hereda tus permisos**. En Drive,
abre la carpeta que tiene los `reporte_personas_completo_*.parquet`, dale
**Compartir**, pega el `client_email` del paso 6 y dale permiso de **Lector**.

> Si la carpeta es de otra dependencia y no puedes compartirla, este método no
> sirve y hay que cambiar a OAuth de usuario. Avísame y lo cambio.

### 3. `drive.env` — el id de la carpeta

Copia la plantilla y llena el id:

```bash
cp .secrets/drive.env.ejemplo .secrets/drive.env
```

El id sale de la URL de la carpeta. Si la URL es

```
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz?usp=sharing
```

el id es `1AbCdEfGhIjKlMnOpQrStUvWxYz`. También puedes pegar la URL completa: el
código sabe extraer el id.

---

## Comprobar que quedó bien

```bash
.venv/bin/python -c "from src import drive; print(drive.sincronizar_rnpdno())"
```

Debe imprimir la ruta del Parquet en `input/rnpdno/`. La primera vez lo descarga
(son ~50 MB); después sólo verifica el tamaño y reusa el que ya está en disco.
