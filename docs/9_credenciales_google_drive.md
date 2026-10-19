# 9. Los dos insumos diarios: descarga automática o ruta local

Dos insumos del pipeline —el RNPDNO del notebook 1 y la PUI del notebook 3— se resuelven al
principio de su cuaderno, y hay **dos modos** de resolverlos:

| Insumo | Notebook | En Drive | Qué queda en disco |
|---|---|---|---|
| RNPDNO | 1 | `reporte_personas_completo.parquet`, ~50 MB, nombre fijo | `input/rnpdno/reporte_personas_completo_DDMMAAAA.parquet` |
| PUI | 3 | `reporte_coincidencias_validas_YYYY-MM-DD.zip`, ~9 MB, uno por día | `input/pui/reporte_coincidencias_validas_YYYY-MM-DD.csv` |

**En modo `drive`, los dos tienen que ser del día.** Si el corte disponible no es el de hoy, el
notebook se detiene en vez de dejar que el reporte salga calculado sobre datos viejos.

Este documento es el trámite de una sola vez para habilitar las dos descargas, que comparten
credenciales, y la referencia del modo local. El código está en [src/drive.py](../src/drive.py).

## Modo de insumos: `drive` o `local`

Lo decide `config.MODO_INSUMOS`, una sola línea en [config.py](../config.py):

```python
MODO_INSUMOS = "local"   # o "local"
```

| | `"drive"` (por omisión) | `"local"` |
|---|---|---|
| De dónde sale el insumo | de la carpeta de Google Drive | del archivo exacto que declara `config` |
| Credenciales | sí, OAuth (todo este documento) | **ninguna**: no se importa nada de Google |
| Regla del día | sí, se exige el corte de hoy | **no**: corre el archivo que le señales |
| Si no puede | **se detiene** | **se detiene** |

**Los dos modos son excluyentes y ninguno es el respaldo del otro.** En modo `drive`, si Drive
no responde el proceso se detiene; no se usa por lo bajo el Parquet que haya quedado en
`input/`, porque ese respaldo silencioso es justo lo que convierte una caída de red en un
reporte calculado sobre datos viejos. En modo `local` nunca se intenta descargar nada.

### Correr todo el pipeline sin descargar nada

1. En `config.py`, pon `MODO_INSUMOS = "local"`.
2. Apunta las dos rutas al archivo **exacto** que quieras correr (no se busca por patrón ni se
   toma "el más reciente"; si la ruta no existe, el cuaderno se detiene diciendo cuál falta):

```python
RNPDNO_LOCAL_FILE = RNPDNO_MANUAL_DIR / "reporte_personas_completo_18092026.parquet"
PUI_LOCAL_FILE    = PUI_DIR / "reporte_coincidencias_validas_2026-09-18.csv"
```

   `RNPDNO_LOCAL_FILE` también puede ser el Excel de tres hojas
   (`RNPDNO_MANUAL_DIR / "reporte_personas_01072026.xlsx"`): el notebook 1 reconoce el formato
   por la extensión.
3. Corre los notebooks como siempre. La celda de insumos imprime `📂 Modo local` y la ruta.

Sin tocar `config.py`, lo mismo con variables de entorno —útil para una corrida suelta o para
dejarlo fijo en `.secrets/drive.env`:

```bash
PIPELINE_MODO_INSUMOS=local .venv/bin/jupyter lab
PIPELINE_RNPDNO_ARCHIVO=/ruta/al/corte.parquet   # opcional, si no es la de config
PIPELINE_PUI_ARCHIVO=/ruta/al/corte.csv          # opcional
```

Las rutas relativas se resuelven contra la raíz del proyecto, no contra `notebooks/`.

Dos avisos del modo local:

- **El nombre del CSV de la PUI debe seguir trayendo la fecha** (`..._YYYY-MM-DD.csv`): de ahí
  sale la fecha de corte de la corrida (notebook 3). El Parquet del RNPDNO no la necesita en el
  nombre —su corte sale de `fecha_consulta`—, pero el cuaderno la imprime desde el nombre, así
  que conviene conservar el patrón `reporte_personas_completo_DDMMAAAA.parquet`.
- **Nadie revisa la antigüedad.** Es el punto del modo, y también su riesgo: el reporte saldrá
  con la fecha del archivo que hayas señalado.

### Un modo por fuente

Normalmente las dos fuentes van juntas. Se pueden separar —por ejemplo, bajar el RNPDNO pero
correr con un CSV de la PUI que te pasaron a mano— con `PIPELINE_RNPDNO_MODO` y
`PIPELINE_PUI_MODO`, que ganan sobre `MODO_INSUMOS`. `GDRIVE_RNPDNO_HABILITADO=0` y
`GDRIVE_PUI_HABILITADO=0`, la forma vieja de decir "no bajes nada", siguen funcionando y hoy
significan modo local para esa fuente.

Todo lo que sigue en este documento aplica al modo `drive`.

## Dónde viven las credenciales

Todo lo confidencial va en `.secrets/`, en la raíz del proyecto. Ese directorio tiene tres
candados y **ninguna credencial se versiona**:

| Candado | Qué hace |
|---|---|
| `.gitignore` de la raíz | ignora todo `.secrets/` |
| `.secrets/.gitignore` | lo vuelve a ignorar desde adentro, por si el de la raíz cambia |
| `.claude/settings.json` | `permissions.deny` impide que los asistentes de IA lean o editen esos archivos |

`config.py` sólo conoce las **rutas** de esos archivos. Nunca su contenido.

Archivos que acaban ahí:

```
.secrets/drive.env           ← id de la carpeta de Drive
.secrets/oauth_client.json   ← ID de cliente de escritorio, se baja de Google Cloud
.secrets/oauth_token.json    ← lo escribe el código tras tu primer consentimiento
```

## Por qué OAuth de usuario

Lo natural para automatizar sería una cuenta de servicio, porque corre sin nadie enfrente.
No se puede: la organización tiene activada la política
`iam.disableServiceAccountKeyCreation` y Google Cloud responde *"Se aplicó una política de
la organización que impide la creación de claves para cuentas de servicio en tu empresa"*.
Esa política no va a cambiar, así que OAuth de usuario es **el único camino** y el código no
contempla otro.

Sale ganando por otro lado: la descarga corre **con tu cuenta**, así que ve exactamente las
carpetas que tú ves y nadie tiene que compartir nada con un tercero. Das el consentimiento
una vez en el navegador y el token se refresca solo.

## Trámite

### 1. Proyecto de Google Cloud

En <https://console.cloud.google.com/>, crea un proyecto **dentro de tu organización** (no
"Sin organización": así el proyecto no cuelga de tu cuenta personal y sobrevive a cambios de
personal). Después, **APIs y servicios → Biblioteca → Google Drive API → Habilitar**.

Leer archivos con la Drive API entra en la cuota gratuita. No necesitas activar facturación.

### 2. Pantalla de consentimiento

**APIs y servicios → Pantalla de consentimiento de OAuth**. Elige tipo de usuario
**Interno**. Es importante: "Interno" sólo admite cuentas de tu organización, no requiere
verificación de Google y **el token no caduca a los 7 días**, que es lo que pasa cuando la
app queda como "Externa" en modo *Prueba*.

Llena nombre de la app y correo de contacto. No hace falta agregar permisos en esa pantalla.

### 3. ID de cliente

**APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**, y en
tipo de aplicación elige **Aplicación de escritorio**. Descarga el JSON y muévelo:

```bash
mv ~/Descargas/client_secret_*.json .secrets/oauth_client.json
chmod 600 .secrets/oauth_client.json
```

### 4. Id de las carpetas de Drive del RNPDNO y de la PUI

Hacen falta las dos. Ninguno de los dos ids es secreto, pero las carpetas son internas y el
repo se comparte fuera de la organización, así que viven en `.secrets/drive.env` y no en
`config.py`.

Abre la carpeta que tiene el `reporte_personas_completo.parquet` y copia el id de la URL.
Haz lo mismo con la carpeta de los `.zip` diarios de la PUI.
Si la URL es

```
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz?usp=sharing
```

el id es `1AbCdEfGhIjKlMnOpQrStUvWxYz`. También puedes pegar la URL completa: el código sabe
extraer el id. Crea el archivo de configuración:

```bash
cat > .secrets/drive.env <<'EOF'
# Carpeta de Drive con los reporte_personas_completo_DDMMAAAA.parquet.
# Acepta el id pelón o la URL completa.
GDRIVE_RNPDNO_FOLDER_ID=PEGA_AQUI_EL_ID

# Pon 0 para que esta fuente corra en modo local (lee config.RNPDNO_LOCAL_FILE y
# no toca Drive). Equivale a PIPELINE_RNPDNO_MODO=local.
GDRIVE_RNPDNO_HABILITADO=1

# Nombre exacto del archivo dentro de la carpeta. Sólo hace falta si cambia de nombre.
#GDRIVE_RNPDNO_ARCHIVO=reporte_personas_completo.parquet

# --- PUI (notebook 3) ---
# Carpeta de Drive con los .zip diarios de la PUI. Acepta el id pelón o la URL completa.
GDRIVE_PUI_FOLDER_ID=PEGA_AQUI_EL_ID_DE_LA_PUI

# Pon 0 para que la PUI corra en modo local. Ya vale 1 por omisión.
#GDRIVE_PUI_HABILITADO=1

# --- Modo de insumos ---
# Descomenta para correr TODO el pipeline sin descargar nada, leyendo los archivos
# que declaran config.RNPDNO_LOCAL_FILE y config.PUI_LOCAL_FILE.
#PIPELINE_MODO_INSUMOS=local
#PIPELINE_RNPDNO_ARCHIVO=input/rnpdno/reporte_personas_completo_18092026.parquet
#PIPELINE_PUI_ARCHIVO=input/pui/reporte_coincidencias_validas_2026-09-18.csv
EOF
chmod 600 .secrets/drive.env
```

### 5. Primer consentimiento

```bash
.venv/bin/python -c "from src import drive; print(drive.sincronizar_rnpdno())"
```

Se abre el navegador, inicias sesión con tu cuenta y autorizas el acceso de **sólo lectura**
a Drive. El resultado queda en `.secrets/oauth_token.json` y no se te vuelve a pedir. El
comando termina imprimiendo la ruta del Parquet en `input/rnpdno/`.

A partir de ahí el notebook 1 lo hace solo.

## El RNPDNO en cada corrida (notebook 1)

En Drive la carpeta tiene varios Parquet y el que sirve es el consolidado:

```
reporte_personas.xlsx
reporte_personas_actualizacion_pendiente.parquet
reporte_personas_completo.parquet          ← este
reporte_personas_desaparecidas.parquet
reporte_personas_localizadas.parquet
```

Ese nombre **no lleva fecha**: es fijo y se sobrescribe en cada entrega. Por eso se exige el
nombre exacto (`config.RNPDNO_DRIVE_ARCHIVO`) en vez de adivinar por patrón, y por eso la
fecha del corte hay que sacarla de otro lado. La secuencia es:

1. Busca ese archivo en la carpeta y lee su `modifiedTime`.
2. **Etapa 1 de la regla del día:** si no se subió hoy, se detiene ahí mismo, sin gastar la
   descarga.
3. Si ya está en `input/rnpdno/` el corte de esa fecha y coincide el tamaño, no lo baja.
4. Descarga a un archivo `.parcial`, para que una interrupción no deje en `input/rnpdno/` un
   Parquet truncado que el notebook tomaría por bueno.
5. **Etapa 2 de la regla del día:** lee `fecha_consulta` de lo descargado y confirma que sea
   de hoy. Si no, borra el `.parcial` y se detiene.
6. Renombra el `.parcial` a `reporte_personas_completo_DDMMAAAA.parquet`, con la fecha que
   salió de `fecha_consulta`.
7. Recarga `config` para que `config.RNPDNO_MANUAL_FILE_2` apunte al corte vigente. De ahí
   lo toman el resto del notebook y [src/pipeline/exportacion_llaves.py](../src/pipeline/exportacion_llaves.py).

La copia local sí lleva la fecha en el nombre aunque la de Drive no: así `input/rnpdno/`
conserva el histórico de cortes y el nombre nunca miente sobre lo que hay adentro.

### La regla del día

Es la garantía de que el reporte nunca sale calculado sobre datos de otro día, y por eso se
verifica dos veces con fuentes distintas:

| Etapa | Fuente | Cuándo | Para qué |
|---|---|---|---|
| 1 | `modifiedTime` de Drive | antes de descargar | corta temprano y no gasta 50 MB en vano |
| 2 | `fecha_consulta` del Parquet | después de descargar | es el corte real, y manda sobre la etapa 1 |

`fecha_consulta` es la marca de tiempo con la que el RNPDNO generó la extracción, idéntica en
las 409,241 filas, y es la misma que el notebook usa para fechar el reporte. `modifiedTime`
sólo dice cuándo se subió el archivo, que es un buen filtro barato pero no es el corte.

La regla no tiene escapatoria por accidente:

- Si Drive sí respondió pero lo que tiene es de ayer, **se detiene**. El riesgo es el que
  importa: que todavía no exista el corte de hoy.
- Si Drive **no** responde, también se detiene. No se reusa el Parquet que haya en
  `input/rnpdno/`: eso sería convertir una falla de red en un reporte viejo sin que nadie lo
  pidiera.

Para reprocesar un corte anterior a propósito hay dos caminos, los dos explícitos: subir
`RNPDNO_DIAS_TOLERANCIA` en `config.py`, o correr en modo `local` apuntando a ese corte.
Las dos tolerancias (`RNPDNO_DIAS_TOLERANCIA` y `PUI_DIAS_TOLERANCIA`) se leen sólo de
`config.py`: si tu `.secrets/drive.env` todavía trae `GDRIVE_RNPDNO_DIAS_TOLERANCIA` o
`GDRIVE_PUI_DIAS_TOLERANCIA`, ya no hacen nada y puedes borrar esas líneas.

## La PUI en cada corrida (notebook 3)

Aquí es más simple, porque el nombre remoto **sí** trae la fecha. La carpeta guarda un zip por
día (`reporte_coincidencias_validas_YYYY-MM-DD.zip`, ~9 MB) que se sube puntualmente a las
08:00 hora local, y cada zip trae un único CSV con ese mismo nombre base.

1. Lista la carpeta y se queda con el zip de fecha más alta, ordenando por la fecha **parseada**
   y no por el texto. Con el formato ISO los dos órdenes coinciden, pero depender de esa
   coincidencia es frágil: basta que un día suban otro formato para que el orden alfabético
   entregue el archivo equivocado sin avisar.
2. **Regla del día:** si ese zip no es de hoy, se detiene sin descargar nada.
3. Si el CSV de ese corte ya está en `input/pui/`, no baja nada. No se compara el tamaño contra
   Drive —allá está comprimido y aquí no—; el nombre ya fija el corte, y el contenido de un
   corte cerrado no cambia.
4. Baja el zip a un directorio temporal, comprueba que traiga exactamente un `.csv` y que el
   nombre de adentro declare el mismo día que el zip, y lo descomprime a `input/pui/`. Lo que
   se conserva es el CSV; el zip se descarta.
5. Recarga `config` para que `config.PUI_COINCIDENCIAS_FILE` apunte al corte vigente.

La descompresión no usa `extractall`: se lee el miembro y se escribe en la ruta que decide el
código, así que un nombre interno con rutas (`../..`) no puede escribir fuera de `input/pui/`.

Los CSV pesan ~59 MB cada uno y **se van acumulando**: `input/pui/` crece un archivo por día.
No se borra nada solo, a propósito —son datos, no basura—, pero conviene podar los cortes
viejos de vez en cuando.

## Si algo falla

**"Falta el ID de cliente de OAuth"** — no está `.secrets/oauth_client.json`. Paso 3.

**"Falta GDRIVE_RNPDNO_FOLDER_ID"** — falta o está vacío `.secrets/drive.env`. Paso 4.

**"En la carpeta de Drive no está 'reporte_personas_completo.parquet'"** — el id apunta a
otra carpeta, o el archivo cambió de nombre. El mensaje lista lo que sí hay ahí. Si el nombre
cambió de forma permanente, ajusta `GDRIVE_RNPDNO_ARCHIVO` en `.secrets/drive.env`.

**Se vuelve a abrir el navegador cada semana** — la pantalla de consentimiento quedó como
"Externa" en modo *Prueba*, donde Google caduca el token a los 7 días. Cámbiala a
**Interno** (paso 2).

**"MODO LOCAL (RNPDNO): el archivo declarado no existe"** — corres en modo local y la ruta de
`config.RNPDNO_LOCAL_FILE` (o de `PUI_LOCAL_FILE`) no apunta a nada. El mensaje trae la ruta
completa. Coloca ahí el archivo, corrige la ruta, o vuelve al modo `drive` para que se baje.

**"El modo 'drive' NO cae al Parquet que haya en input/rnpdno/"** — Drive no respondió y el
pipeline se detuvo en vez de correr con lo que hubiera en disco. Si es un problema de red
pasajero, vuelve a intentar; si quieres correr ya mismo con un archivo que ya tienes, cámbiate
a modo `local` y declara la ruta.

**"PIPELINE_MODO_INSUMOS = 'x' no es un modo de insumos válido"** — sólo existen `drive` y
`local`. `config.py` se detiene al importarse para que el error no aparezca tres celdas después.

**"NO SE TIENE EL ARCHIVO DEL DÍA"** — el corte más nuevo que hay no es de hoy. El mensaje
dice de qué día es y cuántos días de atraso lleva. Lo normal es que el RNPDNO todavía no
haya subido el corte a Drive: súbelo y vuelve a correr. Si de verdad quieres reprocesar un
corte anterior, sube `RNPDNO_DIAS_TOLERANCIA` (o `PUI_DIAS_TOLERANCIA`, para la PUI) en
`config.py`.

**"No se puede saber de qué día es el archivo"** — el nombre del Parquet no cumple
`reporte_personas_completo_DDMMAAAA.parquet`, así que no hay forma de verificar el corte.
Renómbralo al patrón.

**"En la carpeta de Drive de la PUI no hay ningún reporte_coincidencias_validas_..."** —
cambió el nombre de los zips o el id de la carpeta. El mensaje lista los últimos nombres que sí
hay. Ajusta `GDRIVE_PUI_FOLDER_ID` o avisa para cambiar el patrón.

**"Se esperaba exactamente un .csv dentro de ..."** — el zip del día trae más de un archivo o
ninguno. Es un cambio de formato del lado de quien lo sube; el mensaje lista lo que venía.

**"El zip dice ser del X pero adentro trae ..."** — empaquetaron el día equivocado. El proceso
se detiene porque el nombre del zip estaría mintiendo sobre su contenido.

**Quieres forzar la descarga** aunque el archivo ya esté en disco:

```python
drive.sincronizar_rnpdno(forzar=True)   # RNPDNO
drive.sincronizar_pui(forzar=True)      # PUI
```

**Quieres revocar el acceso** que le diste: <https://myaccount.google.com/permissions>, y
borra `.secrets/oauth_token.json`.
