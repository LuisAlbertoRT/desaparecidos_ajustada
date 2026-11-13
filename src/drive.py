"""De dónde salen los dos insumos diarios: de Google Drive, o de una ruta local.

Dos insumos, dos carpetas, dos formatos:

    sincronizar_rnpdno()  → notebook 1. Un Parquet de ~50 MB, nombre fijo en Drive.
    sincronizar_pui()     → notebook 3. Un zip diario de ~9 MB con un CSV adentro.

Las dos funciones devuelven la ruta del insumo listo para leer, y las dos empiezan
preguntando en qué modo corre el pipeline (`config.MODO_INSUMOS`).

Los dos modos son excluyentes
-----------------------------
    "drive"  Se baja el insumo del día de Google Drive. Si Drive no responde, o lo
             que hay no es del día, el proceso SE DETIENE. A propósito no se cae al
             archivo que haya en disco: ese respaldo silencioso es justo lo que
             convierte una caída de red en un reporte calculado sobre datos viejos.

    "local"  Se lee el archivo EXACTO declarado en `config.RNPDNO_LOCAL_FILE` /
             `config.PUI_LOCAL_FILE`. No se importa ninguna librería de Google, no se
             piden credenciales, no se abre el navegador y no se revisa la fecha del
             corte: quien escribió la ruta ya sabe qué archivo está corriendo. Si el
             archivo no está, se detiene diciendo cuál falta.

Ninguno es el respaldo del otro: el modo que no se eligió no se intenta nunca. Todo
lo que sigue en este docstring describe el modo "drive".

Los dos insumos deben llegar a diario, y los dos se detienen si el corte que hay no
es el del día (ver "El corte tiene que ser el del día"), cada uno con su tolerancia.

Credenciales
------------
Nada confidencial vive en el repositorio. Todo se lee de `.secrets/`, que está
fuera de git y bloqueado para los asistentes de IA. El trámite completo está en
`docs/9_credenciales_google_drive.md`.

La autenticación es OAuth de usuario, con dos archivos:

    .secrets/oauth_client.json  ← ID de cliente de escritorio, se baja de Google Cloud
    .secrets/oauth_token.json   ← lo genera el primer consentimiento; se refresca solo

Es decir, la descarga corre CON TU CUENTA: ve exactamente las carpetas que tú ves,
sin que nadie tenga que compartir nada con un tercero. Una cuenta de servicio no es
opción: la organización tiene activada `iam.disableServiceAccountKeyCreation` y no
deja generar la llave JSON.

`config.py` sólo conoce las RUTAS de estos archivos, nunca su contenido.

El corte tiene que ser el del día
---------------------------------
En las dos fuentes, si el corte disponible no es el de hoy el proceso se detiene en
vez de dejar correr el reporte sobre datos viejos. Cómo se averigua la fecha cambia
según lo que dé cada carpeta.

**PUI** (`sincronizar_pui`): fácil, el nombre del zip trae la fecha y es fiable —hay
uno por día, subido a las 08:00 hora local—, así que basta con leerla del nombre.

**RNPDNO** (`sincronizar_rnpdno`): el archivo se llama siempre igual y se sobrescribe,
así que el nombre remoto NO dice de qué día es. La fecha se verifica en dos etapas:

1. Antes de descargar, con `modifiedTime` de Drive: si el archivo no se subió hoy,
   se para ahí y no se gastan los ~50 MB.
2. Después de descargar, con `fecha_consulta` del propio Parquet: la marca con la que
   el RNPDNO generó la extracción, que es el corte de verdad. Es la que manda, y es
   también la que da nombre a la copia local.

El margen lo abre `config.RNPDNO_DIAS_TOLERANCIA` (0 = sólo el corte del día).

La copia local sí lleva la fecha en el nombre
---------------------------------------------
Se guarda como `reporte_personas_completo_DDMMAAAA.parquet`, con la fecha que salió
de `fecha_consulta`. Así el directorio `input/rnpdno/` conserva el histórico de
cortes, `config.RNPDNO_MANUAL_FILE_2` sabe cuál es el vigente, y el nombre nunca
miente sobre lo que hay adentro.
"""

from datetime import date, datetime
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

import config

# Sólo lectura: esto nunca necesita (ni debe) poder escribir en Drive.
ALCANCES = ["https://www.googleapis.com/auth/drive.readonly"]

# La URL de una carpeta de Drive trae el id después de /folders/.
_RE_URL_CARPETA = re.compile(r"/folders/([A-Za-z0-9_-]+)")


def extraer_id_carpeta(valor: str) -> str:
    """Devuelve el id de la carpeta, venga pelón o dentro de una URL de Drive."""
    valor = (valor or "").strip()
    if not valor:
        return ""
    encontrado = _RE_URL_CARPETA.search(valor)
    return encontrado.group(1) if encontrado else valor


# ─── Autenticación ────────────────────────────────────────────────────────────

def _credenciales_usuario(ruta_cliente: Path, ruta_token: Path, verbose: bool = True):
    """Credenciales de TU cuenta de Google, por el flujo OAuth de aplicación de escritorio.

    La primera vez abre el navegador para que des el consentimiento y guarda el
    resultado en `ruta_token`. De ahí en adelante ese token se refresca solo y ya
    no se vuelve a abrir el navegador.
    """
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    credenciales = None
    if ruta_token.is_file():
        try:
            credenciales = Credentials.from_authorized_user_file(str(ruta_token), ALCANCES)
        except ValueError:
            # Token corrupto o de otra versión: se descarta y se pide de nuevo.
            credenciales = None

    if credenciales and credenciales.expired and credenciales.refresh_token:
        try:
            credenciales.refresh(Request())
        except RefreshError:
            # Consentimiento revocado, o token caducado porque la pantalla de
            # consentimiento quedó en modo "Prueba" (ahí el refresh dura 7 días).
            if verbose:
                print("⚠️  El token de Google ya no sirve. Se vuelve a pedir tu consentimiento.")
            credenciales = None

    if not credenciales or not credenciales.valid:
        if verbose:
            print("🔐 Se abrirá el navegador para que autorices el acceso de sólo lectura a Drive.")
        flujo = InstalledAppFlow.from_client_secrets_file(str(ruta_cliente), ALCANCES)
        # port=0 toma un puerto libre; el cliente de escritorio acepta cualquier localhost.
        credenciales = flujo.run_local_server(
            port=0,
            prompt="consent",  # fuerza que Google entregue refresh_token, no sólo el de acceso
            authorization_prompt_message="Abre esta liga si el navegador no se abre solo:\n{url}",
            success_message="Listo. Ya puedes cerrar esta pestaña y volver al notebook.",
        )
        ruta_token.parent.mkdir(parents=True, exist_ok=True)
        ruta_token.write_text(credenciales.to_json())
        ruta_token.chmod(0o600)
        if verbose:
            print(f"✅ Consentimiento guardado en {ruta_token}. No se te volverá a pedir.")

    return credenciales


def _servicio(verbose: bool = True):
    """Cliente de la API de Drive autenticado con tu cuenta. Ver el docstring del módulo."""
    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        raise ImportError(
            "Faltan las librerías de Google. Instálalas con:\n"
            "    pip install -r requirements.txt"
        ) from e

    ruta_cliente = Path(config.RNPDNO_DRIVE_OAUTH_CLIENTE)
    if not ruta_cliente.is_file():
        raise FileNotFoundError(
            f"Falta el ID de cliente de OAuth: {ruta_cliente}\n"
            "El trámite está en docs/9_credenciales_google_drive.md"
        )

    credenciales = _credenciales_usuario(
        ruta_cliente, Path(config.RNPDNO_DRIVE_OAUTH_TOKEN), verbose=verbose
    )
    # cache_discovery=False evita el warning de oauth2client en entornos sin caché.
    return build("drive", "v3", credentials=credenciales, cache_discovery=False)


# ─── Drive ────────────────────────────────────────────────────────────────────

def listar_archivos(servicio, carpeta_id: str) -> list[dict]:
    """Todos los archivos vivos de la carpeta (pagina hasta terminar).

    `supportsAllDrives` / `includeItemsFromAllDrives` hacen falta cuando la
    carpeta vive en una unidad compartida y no en "Mi unidad".
    """
    archivos: list[dict] = []
    token = None
    while True:
        respuesta = (
            servicio.files()
            .list(
                q=f"'{carpeta_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, size, modifiedTime)",
                pageSize=1000,
                pageToken=token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        archivos.extend(respuesta.get("files", []))
        token = respuesta.get("nextPageToken")
        if not token:
            return archivos


def buscar_archivo(archivos: list[dict], nombre: str) -> dict:
    """El archivo de la carpeta que se llama exactamente `nombre`.

    La carpeta trae varios Parquet (desaparecidas, localizadas, pendientes) y sólo
    el consolidado sirve, así que se exige el nombre exacto en vez de adivinar.
    """
    coincidencias = [a for a in archivos if a["name"] == nombre]
    if not coincidencias:
        hay = ", ".join(sorted(a["name"] for a in archivos)) or "(carpeta vacía)"
        raise ValueError(
            f"En la carpeta de Drive no está '{nombre}'.\nLo que hay: {hay}\n"
            "Si el archivo cambió de nombre, ajusta GDRIVE_RNPDNO_ARCHIVO en .secrets/drive.env."
        )
    if len(coincidencias) > 1:
        raise ValueError(
            f"Hay {len(coincidencias)} archivos llamados '{nombre}' en la carpeta de Drive.\n"
            "Drive permite nombres repetidos; borra o renombra los sobrantes para que no "
            "haya duda de cuál es el insumo."
        )
    return coincidencias[0]


def fecha_modificacion(archivo: dict) -> date:
    """Día en que el archivo se subió o actualizó en Drive, en hora local.

    Drive entrega `modifiedTime` en UTC (RFC 3339). Se convierte a la zona horaria
    de esta máquina antes de quedarse con el día: en México, un archivo subido a las
    19:00 aparece como del día siguiente si se lee en UTC.
    """
    marca = datetime.fromisoformat(archivo["modifiedTime"].replace("Z", "+00:00"))
    return marca.astimezone().date()


# ─── La regla del día ─────────────────────────────────────────────────────────

def _exigir_del_dia(
    corte: date,
    origen: str,
    nota: str,
    tolerancia: int,
    donde: str,
    hoy: date | None = None,
) -> date:
    """Detiene el proceso si `corte` no es del día. `origen` dice de dónde salió la fecha.

    `tolerancia` y `donde` (dónde se cambia, para el mensaje) los pone cada fuente:
    el RNPDNO y la PUI deben llegar las dos a diario, pero las suben áreas distintas
    y no fallan el mismo día, así que cada una afloja su margen por separado.
    """
    hoy = hoy or date.today()
    atraso = (hoy - corte).days
    if atraso <= tolerancia:
        return corte

    plural = "día" if atraso == 1 else "días"
    raise RuntimeError(
        "NO SE TIENE EL ARCHIVO DEL DÍA. El proceso se detiene.\n"
        f"  Corte disponible: {corte:%d/%m/%Y}  (según {origen})\n"
        f"  Hoy:              {hoy:%d/%m/%Y}  → {atraso} {plural} de atraso\n"
        f"  Tolerancia:       {tolerancia} días ({donde})\n"
        f"\n{nota}\n"
        "Corriendo así, el reporte saldría calculado sobre datos de otro día.\n"
        "Si de verdad quieres reprocesar un corte anterior, sube la tolerancia."
    )


def fecha_consulta(ruta: Path) -> date:
    """El corte que declara el propio Parquet, en su columna `fecha_consulta`.

    Es la marca de tiempo con la que el RNPDNO generó la extracción, idéntica en
    todas las filas, y es la fecha que el notebook usa para fechar el reporte. Se
    lee sólo esa columna, así que no cuesta cargar el archivo entero.
    """
    import pandas as pd

    try:
        columna = pd.read_parquet(ruta, columns=["fecha_consulta"])["fecha_consulta"]
    except (KeyError, ValueError) as e:
        raise RuntimeError(
            f"El Parquet {ruta.name} no trae la columna 'fecha_consulta', así que no hay "
            "forma de saber de qué corte es. El proceso se detiene."
        ) from e

    marca = pd.to_datetime(columna.dropna(), errors="coerce", utc=True).max()
    if pd.isna(marca):
        raise RuntimeError(
            f"La columna 'fecha_consulta' de {ruta.name} está vacía o no es una fecha. "
            "El proceso se detiene."
        )
    return marca.date()


# ─── Modo local ───────────────────────────────────────────────────────────────

def _insumo_local(ruta, fuente: str, constante: str, variable: str, verbose: bool = True) -> Path:
    """El archivo que declara config, sin tocar Drive. Ver "Los dos modos" arriba.

    No verifica la fecha del corte: en modo local la ruta se escribe a mano y el
    archivo que diga es el que se corre, sea del día que sea.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(
            f"MODO LOCAL ({fuente}): el archivo declarado no existe.\n"
            f"  Ruta:     {ruta}\n"
            f"  Se fija en config.{constante}, o con {variable} en el entorno.\n"
            "En modo local no se baja nada de Drive: coloca ahí el archivo, corrige la\n"
            f"ruta, o vuelve al modo 'drive' (config.MODO_INSUMOS) para que se descargue."
        )
    if verbose:
        print(f"📂 Modo local ({fuente}): no se consulta Google Drive.")
        print(f"   {ruta}  ({ruta.stat().st_size / 1e6:,.1f} MB)")
        print("   No se revisa que el corte sea el del día; corre tal cual.")
    return ruta


# ─── Punto de entrada ─────────────────────────────────────────────────────────

def sincronizar_rnpdno(
    carpeta_id: str | None = None,
    destino_dir: Path | None = None,
    forzar: bool = False,
    verbose: bool = True,
    hoy: date | None = None,
) -> Path:
    """Devuelve la ruta del Parquet del RNPDNO con el que va a correr el notebook 1.

    En modo local es el archivo que declara `config.RNPDNO_LOCAL_FILE`, sin tocar
    Drive. En modo drive se baja de la carpeta de Drive y queda en `input/rnpdno/`.

    En modo drive levanta RuntimeError si el corte disponible no es el de hoy (ver
    "El corte tiene que ser el del día") y también si Drive no responde: no se cae al
    Parquet que haya en disco. Para correr con un archivo local, es el otro modo.

    Reusa el archivo local cuando ya corresponde al corte que Drive tiene y coincide
    el tamaño, así que correr el notebook dos veces seguidas no vuelve a bajar los
    ~50 MB. Con `forzar=True` descarga de todos modos.
    """
    if config.RNPDNO_MODO_INSUMOS == "local":
        return _insumo_local(
            config.RNPDNO_LOCAL_FILE, "RNPDNO",
            "RNPDNO_LOCAL_FILE", "PIPELINE_RNPDNO_ARCHIVO", verbose=verbose,
        )

    hoy = hoy or date.today()
    carpeta_id = extraer_id_carpeta(carpeta_id or config.RNPDNO_DRIVE_FOLDER_ID)
    destino_dir = Path(destino_dir or config.RNPDNO_MANUAL_DIR)
    TOLERANCIA = (config.RNPDNO_DIAS_TOLERANCIA, "config.RNPDNO_DIAS_TOLERANCIA en config.py")

    def _detener(motivo: str) -> Path:
        """Modo drive y Drive no dio el archivo: se para aquí, no hay plan B."""
        raise RuntimeError(
            f"{motivo}\n"
            "El modo 'drive' NO cae al Parquet que haya en input/rnpdno/: correr con "
            "un archivo viejo\nsin haberlo pedido es exactamente el error que esta "
            "regla evita.\n"
            "Si quieres correr con un archivo que ya tienes, pon config.MODO_INSUMOS = "
            "'local'\n(o corre con PIPELINE_MODO_INSUMOS=local) y declara la ruta en "
            "config.RNPDNO_LOCAL_FILE."
        )

    if not carpeta_id:
        return _detener(
            "Falta GDRIVE_RNPDNO_FOLDER_ID en .secrets/drive.env "
            "(ver docs/9_credenciales_google_drive.md)."
        )

    try:
        servicio = _servicio(verbose=verbose)
        remoto = buscar_archivo(
            listar_archivos(servicio, carpeta_id), config.RNPDNO_DRIVE_ARCHIVO
        )
    except (FileNotFoundError, ImportError, ValueError):
        # Errores de configuración: que se vean tal cual, no como "falló la red".
        raise
    except Exception as e:
        return _detener(f"No se pudo consultar Google Drive: {type(e).__name__}: {e}")

    # --- Etapa 1: la fecha de Drive, antes de gastar la descarga ---
    subido = fecha_modificacion(remoto)
    _exigir_del_dia(
        subido,
        f"modifiedTime de {remoto['name']} en Drive",
        "Todavía no han subido el corte de hoy a la carpeta de Drive.",
        *TOLERANCIA, hoy=hoy,
    )

    tam_remoto = int(remoto["size"]) if remoto.get("size") else None
    destino = destino_dir / config.nombre_local_rnpdno(subido)

    # --- ¿Ya está en disco? ---
    if destino.is_file() and not forzar and (tam_remoto is None or destino.stat().st_size == tam_remoto):
        if verbose:
            print(f"✅ {destino.name} ya está al día "
                  f"({destino.stat().st_size / 1e6:,.1f} MB). No se descarga.")
        _exigir_del_dia(
            fecha_consulta(destino), f"fecha_consulta de {destino.name}",
            "El archivo que está en disco no es el corte de hoy.",
            *TOLERANCIA, hoy=hoy,
        )
        return destino

    if verbose:
        mb = f"{tam_remoto / 1e6:,.1f} MB" if tam_remoto else "tamaño desconocido"
        print(f"⬇️  {remoto['name']} en Drive, actualizado el {subido:%d/%m/%Y} ({mb})")

    try:
        parcial = _descargar(servicio, remoto, destino_dir, verbose=verbose)
    except Exception as e:
        return _detener(f"Falló la descarga de {remoto['name']}: {type(e).__name__}: {e}")

    # --- Etapa 2: la fecha que declara el archivo, antes de darlo por bueno ---
    try:
        corte = _exigir_del_dia(
            fecha_consulta(parcial),
            f"fecha_consulta dentro de {remoto['name']}",
            "El archivo de Drive se subió hoy, pero por dentro trae un corte anterior.",
            *TOLERANCIA, hoy=hoy,
        )
    except RuntimeError:
        # No se deja el descarte en input/: sólo ahí viven los cortes buenos.
        parcial.unlink(missing_ok=True)
        raise

    # El nombre local lo pone `fecha_consulta`, no `modifiedTime`: así nunca miente.
    destino = destino_dir / config.nombre_local_rnpdno(corte)
    parcial.replace(destino)
    if verbose:
        print(f"✅ Corte del {corte:%d/%m/%Y} guardado en {destino.name}")
    return destino


def _descargar(servicio, archivo: dict, destino_dir: Path, verbose: bool = True) -> Path:
    """Baja el archivo a un `.parcial` en `destino_dir` y devuelve esa ruta.

    Queda como temporal a propósito: el nombre definitivo depende de `fecha_consulta`,
    que sólo se conoce leyendo lo descargado, y así una descarga interrumpida tampoco
    deja en `input/rnpdno/` un Parquet truncado que el notebook tomaría por bueno.
    """
    from googleapiclient.http import MediaIoBaseDownload

    destino_dir.mkdir(parents=True, exist_ok=True)
    parcial = destino_dir / (archivo["name"] + ".parcial")

    peticion = servicio.files().get_media(fileId=archivo["id"], supportsAllDrives=True)
    with open(parcial, "wb") as salida:
        bajador = MediaIoBaseDownload(salida, peticion, chunksize=16 * 1024 * 1024)
        terminado = False
        while not terminado:
            estado, terminado = bajador.next_chunk()
            if verbose and estado:
                print(f"\r   Descargando… {estado.progress() * 100:5.1f}%", end="")
    if verbose:
        print("\r   Descargando… 100.0%")

    return parcial


# ─── PUI · notebook 3 ─────────────────────────────────────────────────────────
# Otra carpeta de Drive, otro formato: aquí llega un .zip diario
# (`reporte_coincidencias_validas_YYYY-MM-DD.zip`) con un único .csv adentro.
#
# A diferencia del RNPDNO, el nombre remoto SÍ lleva la fecha, y es fiable: hay un
# archivo por día, subido a las 08:00 hora local. Así que la fecha sale del nombre
# y no hace falta la doble verificación con `modifiedTime`.

def elegir_zip_pui(archivos: list[dict]) -> dict:
    """El zip de la PUI con la fecha más alta en el nombre.

    Se ordena por la fecha PARSEADA, no por el texto. Con el formato ISO de esta
    carpeta los dos órdenes coinciden, pero depender de esa coincidencia es frágil:
    basta que algún día suban un nombre con otro formato para que el orden de texto
    entregue el archivo equivocado sin avisar.
    """
    candidatos = []
    for archivo in archivos:
        if not archivo["name"].lower().endswith(".zip"):
            continue
        corte = config.fecha_corte_pui(archivo["name"])
        if corte is not None:
            candidatos.append((corte, archivo))

    if not candidatos:
        hay = sorted(a["name"] for a in archivos)
        muestra = ", ".join(hay[-5:]) if hay else "(carpeta vacía)"
        raise ValueError(
            "En la carpeta de Drive de la PUI no hay ningún "
            "'reporte_coincidencias_validas_YYYY-MM-DD.zip'.\n"
            f"Últimos nombres que sí hay ({len(hay)} archivos): {muestra}"
        )

    corte, archivo = max(candidatos, key=lambda par: par[0])
    archivo["fecha_corte"] = corte
    return archivo


def _extraer_csv(ruta_zip: Path, destino: Path, corte: date, verbose: bool = True) -> Path:
    """Saca el único CSV del zip y lo deja en `destino`.

    No se usa `extractall`: se lee el miembro y se escribe en la ruta que decide este
    código, así que un nombre interno con rutas ('../..') no puede escribir fuera de
    `destino`. Se pasa por un `.parcial` para no dejar un CSV a medias si algo falla.
    """
    with zipfile.ZipFile(ruta_zip) as zf:
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            contenido = ", ".join(zf.namelist()) or "(vacío)"
            raise RuntimeError(
                f"Se esperaba exactamente un .csv dentro de {ruta_zip.name} y hay "
                f"{len(csvs)}.\nContenido del zip: {contenido}"
            )
        interno = csvs[0]

        # El CSV de adentro debe declarar el mismo corte que el zip. Si no coinciden,
        # alguien empaquetó el día equivocado y el nombre del zip estaría mintiendo.
        corte_interno = config.fecha_corte_pui(Path(interno).name)
        if corte_interno != corte:
            raise RuntimeError(
                f"El zip dice ser del {corte:%d/%m/%Y} pero adentro trae "
                f"'{Path(interno).name}'.\nEl proceso se detiene: no se puede confiar "
                "en la fecha del archivo."
            )

        destino.parent.mkdir(parents=True, exist_ok=True)
        parcial = destino.parent / (destino.name + ".parcial")
        with zf.open(interno) as origen, open(parcial, "wb") as salida:
            shutil.copyfileobj(origen, salida, 8 * 1024 * 1024)

    parcial.replace(destino)
    if verbose:
        print(f"✅ Corte del {corte:%d/%m/%Y} descomprimido en {destino.name} "
              f"({destino.stat().st_size / 1e6:,.1f} MB)")
    return destino


def sincronizar_pui(
    carpeta_id: str | None = None,
    destino_dir: Path | None = None,
    forzar: bool = False,
    verbose: bool = True,
    hoy: date | None = None,
) -> Path:
    """Devuelve la ruta del CSV de coincidencias con el que va a correr el notebook 3.

    En modo local es el archivo que declara `config.PUI_LOCAL_FILE`, sin tocar Drive.
    En modo drive baja el zip más reciente de la carpeta, comprueba que sea del día y
    lo descomprime en `input/pui/`. Si ya está el CSV de ese corte, no baja nada.

    En modo drive levanta RuntimeError si el corte disponible no es el de hoy —la
    misma regla del notebook 1, con su propia tolerancia (`config.PUI_DIAS_TOLERANCIA`)—
    y también si Drive no responde: no se cae al CSV que haya en disco.
    """
    if config.PUI_MODO_INSUMOS == "local":
        return _insumo_local(
            config.PUI_LOCAL_FILE, "PUI",
            "PUI_LOCAL_FILE", "PIPELINE_PUI_ARCHIVO", verbose=verbose,
        )

    hoy = hoy or date.today()
    carpeta_id = extraer_id_carpeta(carpeta_id or config.PUI_DRIVE_FOLDER_ID)
    destino_dir = Path(destino_dir or config.PUI_DIR)
    TOLERANCIA = (config.PUI_DIAS_TOLERANCIA, "config.PUI_DIAS_TOLERANCIA en config.py")

    def _detener(motivo: str) -> Path:
        """Modo drive y Drive no dio el archivo: se para aquí, no hay plan B."""
        raise RuntimeError(
            f"{motivo}\n"
            "El modo 'drive' NO cae al CSV que haya en input/pui/: correr con un corte "
            "viejo sin\nhaberlo pedido es exactamente el error que esta regla evita.\n"
            "Si quieres correr con un archivo que ya tienes, pon config.MODO_INSUMOS = "
            "'local'\n(o corre con PIPELINE_MODO_INSUMOS=local) y declara la ruta en "
            "config.PUI_LOCAL_FILE."
        )

    if not carpeta_id:
        return _detener("Falta GDRIVE_PUI_FOLDER_ID (ver docs/9_credenciales_google_drive.md).")

    try:
        servicio = _servicio(verbose=verbose)
        remoto = elegir_zip_pui(listar_archivos(servicio, carpeta_id))
    except (FileNotFoundError, ImportError, ValueError):
        # Errores de configuración: que se vean tal cual, no como "falló la red".
        raise
    except Exception as e:
        return _detener(f"No se pudo consultar Google Drive: {type(e).__name__}: {e}")

    corte = _exigir_del_dia(
        remoto["fecha_corte"],
        f"el nombre de {remoto['name']} en Drive",
        "Todavía no han subido el corte de hoy a la carpeta de Drive de la PUI.",
        *TOLERANCIA, hoy=hoy,
    )

    destino = destino_dir / config.nombre_local_pui(corte)
    if destino.is_file() and not forzar:
        # No se compara el tamaño contra Drive: allá está comprimido y aquí no. El
        # nombre ya fija el corte, y el contenido de un corte cerrado no cambia.
        if verbose:
            print(f"✅ {destino.name} ya está en disco "
                  f"({destino.stat().st_size / 1e6:,.1f} MB). No se descarga.")
        return destino

    if verbose:
        mb = f"{int(remoto['size']) / 1e6:,.1f} MB" if remoto.get("size") else "tamaño desconocido"
        print(f"⬇️  {remoto['name']} ({mb} comprimido)")

    # El zip se baja a un temporal: lo que se conserva en input/pui/ es el CSV.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ruta_zip = _descargar(servicio, remoto, Path(tmp), verbose=verbose)
            return _extraer_csv(ruta_zip, destino, corte, verbose=verbose)
    except (RuntimeError, zipfile.BadZipFile) as e:
        if isinstance(e, zipfile.BadZipFile):
            return _detener(f"El zip de la PUI llegó corrupto: {e}")
        raise
    except Exception as e:
        return _detener(f"Falló la descarga de {remoto['name']}: {type(e).__name__}: {e}")
