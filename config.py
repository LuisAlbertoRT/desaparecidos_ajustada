import os
import re
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

# No se carga ningún `.env` de la raíz: las credenciales sólo se leen de `.secrets/`
# (ver el bloque de MODO_INSUMOS, más abajo).

# --- RUTAS DE DIRECTORIOS ---
# Definir la raíz del proyecto (basado en la ubicación de este archivo config.py)
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
PLANTILLAS_DIR = INPUT_DIR / "plantillas"

# Crear directorios si no existen
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PLANTILLAS_DIR.mkdir(parents=True, exist_ok=True)



# ─── MODO DE INSUMOS: de dónde salen el RNPDNO y la PUI ──────────────────────
# Dos caminos EXCLUYENTES. Ninguno es el respaldo del otro: el que no se eligió no
# se intenta nunca, ni siquiera cuando el elegido falla.
#
#   "drive"  Los notebooks 1 y 3 bajan solos su insumo de Google Drive (src/drive.py)
#            y exigen que el corte sea el del día. Si Drive no responde, el proceso
#            SE DETIENE; no se usa por lo bajo lo que haya quedado en input/, porque
#            eso es justo lo que convierte una caída de red en un reporte viejo.
#
#   "local"  No se toca Drive: no se piden credenciales, no se abre el navegador, no
#            se descarga nada. Se leen los archivos EXACTOS que declaran
#            RNPDNO_LOCAL_FILE y PUI_LOCAL_FILE (abajo, cada uno en su sección) y si
#            falta alguno el notebook se detiene diciendo cuál.
#            Aquí NO se revisa que el corte sea el del día: quien escribe la ruta a
#            mano ya sabe qué archivo está corriendo.
#
# El resto del pipeline no cambia: en los dos modos, los notebooks siguen leyendo
# `config.RNPDNO_MANUAL_FILE_2` y `config.PUI_COINCIDENCIAS_FILE`, que es lo único
# que este modo decide.
MODOS_INSUMOS_VALIDOS = ("drive", "local")

# ← EDITA ESTA LÍNEA para elegir entre "drive" y "local".
# En este entorno lo dejamos en Drive para que intente descargar el insumo de Google Drive.
MODO_INSUMOS = "local"

# Las credenciales y los ids de carpeta viven en `.secrets/`, fuera de git. Se cargan
# aquí arriba —y no junto al bloque de descarga— porque el modo se puede sobrescribir
# desde ese mismo archivo. Ver docs/9_credenciales_google_drive.md.
SECRETS_DIR = BASE_DIR / ".secrets"
load_dotenv(SECRETS_DIR / "drive.env")


def _modo_insumos(valor: str, origen: str) -> str:
    """Valida un modo. Un valor mal escrito se detiene aquí, no tres celdas después."""
    valor = (valor or "").strip().lower()
    if valor not in MODOS_INSUMOS_VALIDOS:
        raise ValueError(
            f"{origen} = {valor!r} no es un modo de insumos válido.\n"
            f"Los únicos son: {', '.join(MODOS_INSUMOS_VALIDOS)}."
        )
    return valor


# Sobrescribir sin tocar este archivo versionado:  PIPELINE_MODO_INSUMOS=local
MODO_INSUMOS = _modo_insumos(
    os.getenv("PIPELINE_MODO_INSUMOS", "").strip() or MODO_INSUMOS,
    "PIPELINE_MODO_INSUMOS" if os.getenv("PIPELINE_MODO_INSUMOS", "").strip() else "config.MODO_INSUMOS",
)

# Modo POR FUENTE. Normalmente los dos van juntos, pero se pueden separar para bajar
# sólo una (p. ej. correr el notebook 3 con un CSV de la PUI que te pasaron a mano,
# sin dejar de bajar el RNPDNO).
#
# `GDRIVE_*_HABILITADO=0` era la forma vieja de decir "no bajes nada"; se sigue
# respetando y significa modo local para esa fuente.
def _descarga_apagada(variable: str) -> bool:
    return os.getenv(variable, "1").strip().lower() in {"0", "false", "no", "off"}


RNPDNO_MODO_INSUMOS = _modo_insumos(
    os.getenv("PIPELINE_RNPDNO_MODO", "").strip()
    or ("local" if _descarga_apagada("GDRIVE_RNPDNO_HABILITADO") else MODO_INSUMOS),
    "PIPELINE_RNPDNO_MODO",
)
PUI_MODO_INSUMOS = _modo_insumos(
    os.getenv("PIPELINE_PUI_MODO", "").strip()
    or ("local" if _descarga_apagada("GDRIVE_PUI_HABILITADO") else MODO_INSUMOS),
    "PIPELINE_PUI_MODO",
)


def _ruta_declarada(variable: str, por_defecto: Path) -> Path:
    """Ruta de un insumo local: la de la variable de entorno, o la escrita aquí.

    Una ruta relativa se resuelve contra la raíz del proyecto, no contra el directorio
    desde el que se lanzó Jupyter (que es `notebooks/` y haría fallar lo obvio).
    """
    valor = os.getenv(variable, "").strip()
    if not valor:
        return por_defecto
    ruta = Path(valor).expanduser()
    return ruta if ruta.is_absolute() else BASE_DIR / ruta


# ─── MOTOR REFINADO (normalizar_folios_v6) ────────────────────────────────────
# Directorio donde se colocan los archivos de revisión del SESNSP.
# Coloca aquí los dos archivos antes de ejecutar el motor 'refinado' o 'manual':
#
#   input/input_reporte_diario/
#       matches_verif_fecha_hechos_SESNSP.xlsx   ← revisiones de fecha de hechos
#       revision_manual_score_SESNSP.xlsx        ← revisiones manuales por score
#
# Los archivos son OPCIONALES: si no existen, el descuento se omite
# silenciosamente y el motor corre sobre el universo completo.
REFINADO_REVISIONES_DIR = INPUT_DIR / "matches_manuales"

REFINADO_RUTA_VERIF_FECHA_HECHOS = REFINADO_REVISIONES_DIR / "matches_verif_fecha_hechos_SESNSP.xlsx"
REFINADO_RUTA_REVISION_MANUAL    = REFINADO_REVISIONES_DIR / "revision_manual_score_SESNSP.xlsx"

# Candidatos de nombre de columna para el archivo matches_verif_fecha_hechos_SESNSP.xlsx.
# Si el archivo cambia de nombre de columnas, ajusta las listas aquí.
# Se normalizan espacios, puntos y guiones antes de comparar.
REFINADO_VERIF_COLUMN_MAPPING = {
    "col_valido":     ["VALIDO", "Válido", "valido"],
    "col_reg_banci":  ["ID registro", "id_registro", "ID.registro",
                       "ID registro banci", "ID banci", "id_registro_banci"],
    "col_fub_rnpdno": ["FUB rnpdno", "fub_rnpdno", "FUB.rnpdno",
                       "ID rnpdno", "fub", "FUB"],
}

# Candidatos de nombre de columna para el archivo revision_manual_score_SESNSP.xlsx.
REFINADO_REVISION_COLUMN_MAPPING = {
    "col_valido":     ["VALIDA", "Válida", "valida"],
    "col_reg_banci":  ["id_registro", "ID registro", "id_registro_banci", "ID.registro"],
    "col_fub_rnpdno": ["fub_rnpdno", "FUB rnpdno", "fub", "FUB"],
}
# ─────────────────────────────────────────────────────────────────────────────







# --- ARCHIVOS AUXILIARES (RENAPO) ---
# Lista de archivos para reconstrucción de CURPs
# Ahora se encuentran en input/cruces_curp/
CRUCES_DIR = INPUT_DIR / "cruces_curp" # Renombrado para claridad, antes solo "input" dentro de scripts
RENAPO_FILES = [
    CRUCES_DIR / "CURP_act260525.csv",
    CRUCES_DIR / "curps_reconstruidas_210625.xlsx",
    CRUCES_DIR / "curps_con_resultado_prueba_01072025.xlsx",
    CRUCES_DIR / "curps_con_resultado_prueba_050825.xlsx"
] 
# --- PARÁMETROS DE VALIDACIÓN (CURP) ---
# Expresiones regulares para validar CURP
CURP_REGEX_FORMAT = r"^[A-Z]{4}\d{6}[HM]"
CURP_REGEX_HOMOCLAVE = r"[A-Z]{3}.{2}$"

# Códigos de estado válidos para CURP
# Extraído de los scripts R
VALID_STATE_CODES = [
    "AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR",
    "HG", "JC", "MC", "MN", "MS", "NT", "NL", "OC", "PL", "QT", "QR", "SP",
    "SL", "SR", "TC", "TS", "TL", "VZ", "YN", "ZS", "NE"
]





# Archivo de BANCI (Secretariado)
# Se define como un único archivo y dirección, según tu solicitud
#BANCI_FILE = INPUT_DIR / "banci" / "SUBIR_R_202606_junio.xlsx"                  #<---- Aquí se cambia la BANCI
#BANCI_FILE = INPUT_DIR / "banci" / "SUBIR_R_202609_septiembre.xlsx"                  #<---- Aquí se cambia la BANCI
BANCI_FILE = INPUT_DIR / "banci" / "SUBIR_R_202610_octubre.xlsx"                #<---- Aquí se cambia la BANCI


# Hoja específica del archivo BANCI (Secretariado)
# Si es None, se lee la hoja predeterminada. Si se le asigna un nombre (string), se lee esa hoja específica.
BANCI_SHEET = 'Victimas'

# Validaciones de la entrega de BANCI (src/validacion_banci.py): la del corte nuevo tiene
# que traer más registros que la anterior, no puede ser de un corte más viejo, ninguna
# entidad puede desaparecer, etc. Con True un problema detiene el notebook 2; con False
# sólo se avisa. Déjalo en True salvo que ya sepas por qué la entrega no cumple (p. ej.
# el Secretariado depuró registros) y vuelve a ponerlo en True después.
VALIDACION_BANCI_ESTRICTA = False

# --- PERÍODOS DE TIEMPO PARA DATAFRAMES GENERADOS ---
# Se definen los límites de fecha para cada período (inicio, fin). None para indicar sin límite (min/max).
# Los nombres corresponden a las abreviaturas de catalogo_abreviaturas.md
PERIODOS_TIEMPO = {
    "min-max": (None, None),
    "min-01ene06": (None, "2006-01-01"),
    "01ene06-max": ("2006-01-01", None),
    "min-01oct24": (None, "2024-10-01"),
    "01oct24-max": ("2024-10-01", None),
    "01ago25-max": ("2025-08-01", None),
    # Añadidos para los marcadores de la plantilla reporte_diario.pptx.
    # Convención [inicio, fin): el límite inferior se incluye, el superior no.
    # "01oct24-01ago25" va del 1 de octubre de 2024 al 31 de julio de 2025.
    "01oct24-01ago25": ("2024-10-01", "2025-08-01"),
    # Corte de agosto de 2026: es el que parten las láminas 13 y 14 del reporte
    # diario. No se confunde con "01ago25-max", que sigue vivo en la lámina 5.
    "01ago26-max": ("2026-08-01", None),
    # Desde el 1 de julio de 2026: la base de los sin carpeta que se manda a
    # revisión manual (notebook 6, PARA_EXPORTAR_CON_FECHA). No es una lámina.
    "01jul26-max": ("2026-07-01", None),
}
BANCI_COLUMN_MAPPING = {
    # Identidad
    'nombres': ['nombres', 'nombre', 'NOMBRES'],
    'primer_apellido': ['primer_apellido', 'paterno', 'apellido_paterno'],
    'segundo_apellido': ['segundo_apellido', 'materno', 'apellido_materno'],
    'curp': ['curp', 'CURP', 'curp_victima'],
    'sexo': ['sexo'],
    'fha_nac': ['fha_nac', 'fecha_nacimiento', 'fecha_nac'],
    
    # Ubicación
    'entidad': ['entidad', 'entidad_federativa', 'estado_reporta', 'entidad_reporta', 'ENTIDAD FEDERATIVA'],
    'id_mun_hchos': ['id_mun_hchos', 'idmunicipio_hechos', 'id_municipio_hechos'],
    # NOMBRE del municipio de los hechos. El motor refinado compara municipios con
    # fuzzy match (UMBRAL_MUNICIPIO = 0.80), pensado para nombres ("GENERAL ESCOBEDO"
    # vs "ESCOBEDO"), NO para claves: `id_mun_hchos` de BANCI e `idmunicipio` del
    # RNPDNO no comparten codificación y su intersección literal es CERO, así que
    # sin esta columna `_muni_igual` era siempre False en toda la corrida.
    'nom_mun_hchos': ['NOM_MUN_HCHOS', 'nom_mun_hchos', 'municipio_hechos',
                      'nombre_municipio_hechos', 'municipio'],
    
    # Fechas
    'fha_de_hchos': ['fha_de_hchos', 'fecha_hechos', 'Fecha Hechos', 'fecha de hechos'],
    'fha_de_ini': ['fha_de_ini', 'fecha_inicio', 'fecha inicio'],
    
    # Estatus
    'localizado_o_no_localizado': ['localizado_o_no_localizado', 'estatus', 'Estatus', 'estatus_localizado'],
    
    # Delitos/Clasificaciones
    'fue_delito': ['fue_delito', 'fue_delito_origen'],
    'delito_hom': ['delito_hom', 'delito_homologado'],
    
    # Claves
    'llave': ['llave'],
    'folio_rnpdno': ['folio_rnpdno', 'folio_rnpdno_ori', 'folio_RNPDNO', 'fub_ok'],
    # Número de Trámite de Carpeta de Investigación → folio para motor refinado
    'ntra_ci': ['NTRA_CI', 'ntra_ci', 'NtraCi'],
    # Identificador secundario de carpeta. normalizar_folios_v6.py lo usa cuando el
    # consecutivo de NTRA_CI tiene <= 2 dígitos (o ninguno): sin él, el 34.6 % de los
    # BANCI no localizados se queda sin consecutivo comparable y nunca puede alcanzar
    # "folio limpio identico".
    'id_ci': ['ID_CI', 'id_ci', 'idci', 'IdCi'],
}






# Catálogo INEGI de municipios (CVE_ENT + CVE_MUN → NOM_MUN).
# Con él se deriva `municipio_derivada_rnpdno`: el RNPDNO sólo trae la clave
# numérica del municipio y el motor refinado compara NOMBRES.
CATALOGO_MUNICIPIOS_FILE = INPUT_DIR / "catalogos_inegi" / "catalogo_municipios_inegi.csv"


# Archivo de Registros Administrativos (Confrontas)
# Lo produce 3_Procesamiento_ETL_PUI.ipynb, igual que los Parquet de los notebooks 1 y 2.
# Antes se entregaba a mano como Excel en input/confrontas/; esa carpeta ya no es parte del
# pipeline. El lector (src/pipeline/carga.py) sigue aceptando .xlsx, así que un perfil puede
# apuntar a un archivo antiguo si hace falta.
# Rutas de lectura y escritura compartidas por los ETL oficiales y el pipeline.
ETL_RNPDNO_INPUT_FILE = OUTPUT_DIR / "Resultado_1_Procesamiento_ETL_RNPDNO.parquet"
ETL_BANCI_INPUT_FILE = OUTPUT_DIR / "Resultado_2_Procesamiento_ETL_BANCI.parquet"
ETL_PUI_INPUT_FILE = OUTPUT_DIR / "Resultado_3_Procesamiento_ETL_PUI.parquet"

# Archivo de Registros Administrativos (Confrontas) que carga el pipeline.
CONFRONTAS_FILE = ETL_PUI_INPUT_FILE
# Mapeos de nombres de columnas para el archivo de confrontas
# Lo que carga.py toma de Resultado_3 (o de un Excel de confrontas entregado a mano,
# que usa los nombres sin sufijo): el FUB y la indicadora de indicio de vida.
CONFRONTAS_COLUMN_MAPPING = {
    'fub': ['fub_derivada_pui', 'fub'],
    'indicadora_registro': ['indicadora_indicio_de_vida_derivada_pui',
                            'indicadora_registro', 'indicadora_indicio_de_vida'],
}


# ─────────────────────────────────────────────────────────────────────────────
# INSUMOS DE LA PUI · notebook 3_Procesamiento_ETL_PUI
# ─────────────────────────────────────────────────────────────────────────────
# Control estricto para los insumos que se entregan a mano (`PUI_REGISTROS_FILE` y
# `PUI_DEFUNCIONES_FILE`): se declara el archivo EXACTO, sin búsqueda por patrón. Si
# no existe, el notebook se detiene con un error; no adivina.
#
# La excepción es `PUI_COINCIDENCIAS_FILE`, que desde que la descarga se automatizó
# sí se resuelve por fecha: llega un corte nuevo cada día y fijarlo a mano obligaría
# a editar este archivo a diario. La garantía de no correr con datos viejos ya no la
# da el nombre escrito aquí, sino la regla del día de src/drive.py.
PUI_DIR = INPUT_DIR / "pui"

# 1. Coincidencias administrativas de la PUI (`coincidencias_admin_con_inactivas`).
#    Lo baja y descomprime 3_Procesamiento_ETL_PUI (ver src/drive.py): en Drive
#    llega como `reporte_coincidencias_validas_YYYY-MM-DD.zip`, uno por día, y el
#    zip trae un único .csv con ese mismo nombre. Aquí se guarda ya descomprimido.
#
#    Como en el RNPDNO, el archivo NO se fija a mano: se toma el de fecha más alta
#    que haya en input/pui/. `PUI_COINCIDENCIAS_RESPALDO` sólo entra cuando no hay
#    ninguno, para que el error diga qué falta en vez de reventar con un nombre vacío.
PUI_COINCIDENCIAS_GLOB = "reporte_coincidencias_validas_*.csv"
PUI_COINCIDENCIAS_REGEX = re.compile(
    r"^reporte_coincidencias_validas_(\d{4})-(\d{2})-(\d{2})\.(?:csv|zip)$"
)
PUI_COINCIDENCIAS_RESPALDO = PUI_DIR / "reporte_coincidencias_validas_2026-09-21.csv"


def fecha_corte_pui(nombre) -> date | None:
    """Fecha que declara el nombre del insumo de la PUI, o None si no es del patrón.

    Sirve igual para el `.zip` de Drive y para el `.csv` ya descomprimido: los dos
    llevan el mismo nombre base. OJO: aquí la fecha va en ISO (YYYY-MM-DD), no en
    DDMMAAAA como la del RNPDNO.
    """
    encontrado = PUI_COINCIDENCIAS_REGEX.match(getattr(nombre, "name", str(nombre)))
    if not encontrado:
        return None
    anio, mes, dia = (int(g) for g in encontrado.groups())
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def nombre_local_pui(corte: date) -> str:
    """Nombre con el que se guarda un corte de la PUI en input/pui/."""
    return f"reporte_coincidencias_validas_{corte:%Y-%m-%d}.csv"


def pui_coincidencias_mas_reciente(directorio=None) -> Path | None:
    """El CSV de la PUI con el corte más reciente EN ESE directorio, o None si no hay."""
    directorio = Path(directorio or PUI_DIR)
    if not directorio.is_dir():
        return None
    candidatos = [
        (corte, ruta)
        for ruta in directorio.glob(PUI_COINCIDENCIAS_GLOB)
        if (corte := fecha_corte_pui(ruta.name)) is not None
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda par: par[0])[1]


# MODO LOCAL: el archivo EXACTO que se lee cuando no se baja nada de Drive. Aquí sí
# se fija a mano, como los demás insumos de control estricto: si la ruta no existe,
# el notebook 3 se detiene diciendo cuál falta, no busca un sustituto.
# Sobrescribir sin editar este archivo:  PIPELINE_PUI_ARCHIVO=input/pui/otro.csv
PUI_LOCAL_FILE = _ruta_declarada(
    "PIPELINE_PUI_ARCHIVO",
    #PUI_DIR / "reporte_coincidencias_validas_2026-07-01.csv",                  # <------ Aquí se cambia el archivo de PUI
    PUI_DIR / "reporte_coincidencias_validas_2026-11-23.csv",                   # <------ Aquí se cambia el archivo de PUI
)

# El insumo que leen el notebook 3 y src/drive.py. En modo "drive" es el corte que
# acaba de bajarse (el más reciente de input/pui/); en modo "local", el declarado
# arriba. Se recalcula en cada `importlib.reload(config)`.
if PUI_MODO_INSUMOS == "local":
    PUI_COINCIDENCIAS_FILE = PUI_LOCAL_FILE
else:
    PUI_COINCIDENCIAS_FILE = pui_coincidencias_mas_reciente() or PUI_COINCIDENCIAS_RESPALDO

# 2. Confrontas manuales del RNPDNO (`registros`), 5 columnas.
#    OJO: no confundir con registros_con_pui_ACTIVOS_*.xlsx, que son salidas
#    antiguas del flujo en R, no insumos.
PUI_REGISTROS_FILE = PUI_DIR / "registros_con_pui_13032026.xlsx"

# 3. Defunciones por institución (`defunciones_df`).
PUI_DEFUNCIONES_FILE = PUI_DIR / "tabla_defunciones_por_institucion_05052026.xlsx"

# 4. CURP que el cruce descarta por inválidas, una por renglón. Son datos personales:
#    viven aquí, fuera de git, y no en el código. Si falta, el notebook 3 avisa y no
#    descarta ninguna.
PUI_CURPS_EXCLUIDAS_FILE = PUI_DIR / "curps_excluidas.txt"

# Hoja de cada insumo Excel de la PUI (0 = la primera). Si el archivo no tiene
# esa hoja, el notebook se detiene.
PUI_REGISTROS_SHEET = 0
PUI_DEFUNCIONES_SHEET = 0

# Columnas EXIGIDAS en cada insumo. Estructura idéntica a RNPDNO_COLUMN_MAPPING y
# BANCI_COLUMN_MAPPING: 'nombre_interno': ['alias_1', 'alias_2', ...].
# Si ninguno de los alias aparece en el archivo, el proceso se detiene diciendo
# cuál falta y qué columnas sí trae.
PUI_COINCIDENCIAS_COLUMN_MAPPING = {
    'institucion_id':     ['institucion_id'],
    'institucion':        ['institucion'],
    'fase_busqueda':      ['fase_busqueda'],
    'fub':                ['fub'],
    'curp':               ['curp'],
    'tipo_evento':        ['tipo_evento'],
    'fecha_evento':       ['fecha_evento'],
    'fecha_desaparicion': ['fecha_desaparicion'],
    'entidad_federativa': ['entidad_federativa'],
    # El script de R acepta los dos nombres y renombra a `created_at`.
    'reporte_created_at': ['reporte_created_at', 'fecha_creacion_reporte'],
    'coincidencia_id':    ['coincidencia_id'],
    'calle':              ['calle'],
    'codigo_postal':      ['codigo_postal'],
    'colonia':            ['colonia'],
    'direccion':          ['direccion'],
    'is_valid':           ['is_valid'],
}

PUI_REGISTROS_COLUMN_MAPPING = {
    'fub':                            ['fub'],
    'curp_victima':                   ['curp_victima', 'curp'],
    'indicadora_indicio_de_vida':     ['indicadora_indicio_de_vida'],
    'institucion_indicadora_de_vida': ['institucion_indicadora_de_vida'],
    'numero_instituciones':           ['numero_instituciones'],
}

PUI_DEFUNCIONES_COLUMN_MAPPING = {
    'fub':                        ['fub'],
    'tipo_defuncion_institucion': ['tipo_defuncion_institucion'],
}

# Columnas que el notebook 3 toma del Parquet del notebook 1 (el `comprimido`).
# `curp_victima` NO existe con ese nombre: la equivalente es
# `curp_vic_derivada_rnpdno`, la CURP IMPUTADA por src.cleaning.imputar_curps.
# No sirve `curp_vic_rnpdno`, la original sin imputar: deja sin CURP a los registros
# que sólo la tienen por imputación (el pipeline de R sí los resuelve).
PUI_COMPRIMIDO_COLUMN_MAPPING = {
    'fub':                     ['fub_rnpdno'],
    'curp_victima':            ['curp_vic_derivada_rnpdno'],
    'clasificacion_des':       ['clasificacion_des_derivada_rnpdno'],
    'fecha_hechos_modificada': ['fecha_hechos_modificada_derivada_rnpdno'],
}

# Fecha del corte de la PUI, en DDMMYYYY. Sólo etiqueta la corrida y sirve para
# localizar el archivo de referencia con el que comparar (ver PUI_REFERENCIA_FILE).
# None = se deriva de la fecha que trae el nombre de PUI_COINCIDENCIAS_FILE.
PUI_FECHA_CORTE = None

# Salida de R con la que contrastar la réplica. None = se omite la comparación.
PUI_REFERENCIA_FILE = None


# ─────────────────────────────────────────────────────────────────────────────
# SALIDAS DE LOS NOTEBOOKS DE ETL
# ─────────────────────────────────────────────────────────────────────────────
# Nombre fijo, sin fecha: destinos de escritura de los ETL oficiales. Los
# consumidores del pipeline usan ETL_*_INPUT_FILE, que apunta a estos mismos destinos.
ETL_RNPDNO_OUTPUT_FILE = OUTPUT_DIR / "Resultado_1_Procesamiento_ETL_RNPDNO.parquet"

# Las columnas de la salida del notebook 1, en orden. Es un contrato: el notebook
# exporta exactamente éstas y src/pipeline/carga.py se niega a cargar un Parquet
# que no las traiga. Siguen la convención de sufijos:
#   `<columna>_rnpdno`          el valor tal como viene del RNPDNO (fechas y claves
#                               como texto; los vacíos y "N/A" se leen como nulo).
#   `<columna>_derivada_rnpdno` cualquier columna transformada o calculada.
# No hay columnas sin sufijo ni alias: cada dato vive en una sola columna.
RNPDNO_OUTPUT_COLUMNS = [
    # Tal como vienen del RNPDNO
    "fub_rnpdno", "estatus_rnpdno", "nombre_vic_rnpdno", "primerapellido_vic_rnpdno",
    "segundoapellido_vic_rnpdno", "sexo_rnpdno", "fechanacimiento_rnpdno",
    "idestadonacimiento_vic_rnpdno", "idestado_rnpdno", "idmunicipio_rnpdno",
    "fechahechos_rnpdno", "fechapercato_rnpdno", "fechalocaliza_rnpdno",
    "delitolocalizacion_rnpdno", "fechacaptura_rnpdno", "dependencia_origen_rnpdno",
    "fecha_consulta_rnpdno", "curp_vic_rnpdno", "expedientes_rnpdno",
    # Transformadas o calculadas
    "fechanacimiento_derivada_rnpdno", "idestado_derivada_rnpdno",
    "idmunicipio_derivada_rnpdno", "fechahechos_derivada_rnpdno",
    "fechapercato_derivada_rnpdno", "fechalocaliza_derivada_rnpdno",
    "fechacaptura_derivada_rnpdno", "fecha_consulta_derivada_rnpdno",
    "curp_vic_derivada_rnpdno", "curp_vic_valida_derivada_rnpdno",
    "nombre_completo_derivada_rnpdno", "fecha_hechos_modificada_derivada_rnpdno",
    "estado_derivada_rnpdno", "clasificacion_des_derivada_rnpdno",
]
ETL_BANCI_OUTPUT_FILE  = OUTPUT_DIR / "Resultado_2_Procesamiento_ETL_BANCI.parquet"

# Las columnas de la salida del notebook 2, en orden. Mismo contrato y misma
# convención que RNPDNO_OUTPUT_COLUMNS: `<columna>_banci` es el valor tal como viene
# del Excel de BANCI (las fechas de inicio y de hechos ya llegan como fecha; la de
# nacimiento, como texto) y `<columna>_derivada_banci` lo transformado. Sólo hay una
# derivada donde la transformación cambia algo y alguien la usa.
BANCI_OUTPUT_COLUMNS = [
    # Tal como vienen de BANCI
    "entidad_banci", "llave_banci", "id_ci_banci", "ntra_ci_banci", "fha_de_ini_banci",
    "fha_de_hchos_banci", "nom_mun_hchos_banci", "id_mun_hchos_banci", "delito_hom_banci",
    "sexo_banci", "fha_nac_banci", "folio_rnpdno_banci", "primer_apellido_banci",
    "segundo_apellido_banci", "nombres_banci", "curp_banci",
    "localizado_o_no_localizado_banci", "fue_delito_banci", "fub_ok_banci",
    # Transformadas o calculadas
    "entidad_derivada_banci", "id_ci_derivada_banci", "ntra_ci_derivada_banci",
    "fha_de_hchos_derivada_banci", "nom_mun_hchos_derivada_banci",
    "localizado_o_no_localizado_derivada_banci", "fha_nac_derivada_banci",
    "nombres_derivada_banci", "primer_apellido_derivada_banci",
    "segundo_apellido_derivada_banci", "nombre_completo_derivada_banci",
    "curp_valida_derivada_banci", "id_carpeta_derivada_banci",
]
ETL_PUI_OUTPUT_FILE    = OUTPUT_DIR / "Resultado_3_Procesamiento_ETL_PUI.parquet"

# Las 10 columnas que arma el notebook 3, en orden, con los nombres del script de R
# (así se compara contra él). Al exportar se renombran con PUI_NOMBRES_EXPORTADOS.
PUI_OUTPUT_COLUMNS = [
    "fub", "curp_victima", "indicadora_indicio_de_vida",
    "institucion_indicadora_de_vida", "numero_instituciones",
    "indicadora_coincidencia_manual", "tipo_tramites", "tramites_repetidos",
    "fecha_evento", "clasificacion_des",
]

# Nombres con que sale Resultado_3: el sufijo dice de qué fuentes viene cada columna.
# Ninguna llega intacta de un archivo de la PUI —todas se agregan por FUB o mezclan
# coincidencias, confrontas manuales y defunciones—, así que todas son `_derivada_`.
# `curp_victima` además toma la CURP imputada del RNPDNO en las filas de defunciones,
# y `clasificacion_des` se copia tal cual de Resultado_1.
PUI_NOMBRES_EXPORTADOS = {
    "fub":                            "fub_derivada_pui",
    "curp_victima":                   "curp_victima_derivada_rnpdno_pui",
    "indicadora_indicio_de_vida":     "indicadora_indicio_de_vida_derivada_pui",
    "institucion_indicadora_de_vida": "institucion_indicadora_de_vida_derivada_pui",
    "numero_instituciones":           "numero_instituciones_derivada_pui",
    "indicadora_coincidencia_manual": "indicadora_coincidencia_manual_derivada_pui",
    "tipo_tramites":                  "tipo_tramites_derivada_pui",
    "tramites_repetidos":             "tramites_repetidos_derivada_pui",
    "fecha_evento":                   "fecha_evento_derivada_pui",
    "clasificacion_des":              "clasificacion_des_derivada_rnpdno",
}


# ─────────────────────────────────────────────────────────────────────────────
# PLANTILLAS Y SALIDAS DE LAS PRESENTACIONES · notebooks 5 y 6
# ─────────────────────────────────────────────────────────────────────────────
PLANTILLA_REPORTE_DIARIO  = PLANTILLAS_DIR / "reporte_diario.pptx"
PLANTILLA_REPORTE_ESTATAL = PLANTILLAS_DIR / "reporte_estados.pptx"

PPT_DIARIO_DIR   = OUTPUT_DIR / "ppt_reporte_diario"
PPT_ESTATAL_DIR  = OUTPUT_DIR / "ppt_reporte_estatal"

# Nombre del archivo del reporte diario. Lleva la fecha del día en que se emite,
# así que cada corrida deja su propio archivo y no pisa la del día anterior.
# El notebook vuelve a componerlo al ejecutarse: si el kernel lleva días abierto,
# `PPT_DIARIO_FILE` se habría quedado con la fecha del día en que se importó.
PPT_DIARIO_NOMBRE = "Reporte de personas desaparecidas - {fecha}.pptx"
PPT_DIARIO_FECHA_FORMATO = "%d.%m.%Y"      # 07.09.2026


def ppt_diario_file(fecha=None) -> Path:
    """Ruta del reporte diario para una fecha (por defecto, hoy)."""
    f = fecha or date.today()
    return PPT_DIARIO_DIR / PPT_DIARIO_NOMBRE.format(
        fecha=f.strftime(PPT_DIARIO_FECHA_FORMATO))


PPT_DIARIO_FILE = ppt_diario_file()


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTORIO DE INDICIOS DE VIDA · lámina 12 del reporte diario
# ─────────────────────────────────────────────────────────────────────────────
# Corte congelado de las personas con indicio de vida al 24/06/2026, con domicilio
# y números de contacto. NO pasa por el pipeline: es una foto fija que se cruza
# contra el RNPDNO vigente para ver cuántos de esos indicios YA SE FORMALIZARON
# como localización (de ahí el token `fmz` = formalizados).
#
# Alimenta estos marcadores de la plantilla:
#     {{reg_rn_24jun26-max_loc_fmz}}      total formalizado, acotado a
#                                         DIRECTORIO_INDICIOS_ESTADOS
#     {{pct_reg_rn_24jun26-max_loc_fmz}}  su porcentaje, contra el total de
#                                         formalizados del país (el `_v2`)
#     {{reg_rn_24jun26-max_loc_fmz_v2}}   el mismo total SIN acotar por entidad:
#                                         el conteo de todo el país
#     {{reg_rn_24jun26-max_loc_fmz_v3}}   el resto del país (`_v2` − el primero)
#     {{gr_ent_rn_24jun26-max_loc_fmz}}   desglose por entidad
#     {{reg_rn_24jun26-max_loc_fmz_v4}}   total formalizado en las 32 entidades
#                                         federativas (sin "Nacido en el
#                                         extranjero"); las 32 salen de ENTIDADES
#     {{gr_32ent_rn_24jun26-max_loc_fmz}} desglose por entidad de esas 32
#     {{reg_rn_24jun26-max_loc_fmz_sisf}} registros sin entidad de desaparición,
#                                         excluidos del desglose por entidad
# Los calcula `src.directorio_indicios.indicios_formalizados`.
DIRECTORIO_INDICIOS_DIR = INPUT_DIR / "domicilios_y_numeros_contacto"
DIRECTORIO_INDICIOS_FILE = (
    DIRECTORIO_INDICIOS_DIR
    / "base_combinada_con_domicilio_y_numeros_de_contacto_24062026.xlsx"
)
DIRECTORIO_INDICIOS_SHEET = 0

# Fecha del corte, en el formato que usan los marcadores. Si cambia el archivo,
# cambia también aquí y los marcadores se renombran solos.
DIRECTORIO_INDICIOS_CORTE = "24jun26"

# Sólo estas dos columnas se usan del archivo (trae 37).
DIRECTORIO_INDICIOS_COLUMN_MAPPING = {
    'fub':                     ['FUB', 'fub'],
    'estado_de_desaparicion':  ['Estado de Desaparición', 'estado_desaparicion',
                                'estado_de_desaparicion'],
}

# Columna del comprimido con la que se decide si el indicio ya se formalizó.
# El análisis original usó `clasificacion_des_rnpdno` (la clasificación CRUDA del
# RNPDNO). Se deja primera por fidelidad, con `clasificacion_des` como alternativa:
# hoy las dos son IDÉNTICAS en las 408,600 filas del Parquet, y la segunda es la
# única que sobrevive a la CAPA B, así que aceptar ambas permite alimentar la
# lámina tanto desde el Parquet del ETL como desde el universo ya construido.
DIRECTORIO_INDICIOS_COMPRIMIDO_COLUMN_MAPPING = {
    'fub':               ['fub_rnpdno'],
    'clasificacion_des': ['clasificacion_des_derivada_rnpdno'],
}

# Clasificaciones que cuentan como "ya localizado" y como "todavía desaparecido".
# Un FUB del directorio que no aparece en el RNPDNO cuenta como todavía desaparecido.
DIRECTORIO_INDICIOS_CLASIF_LOCALIZADO = ["Localizados"]
DIRECTORIO_INDICIOS_CLASIF_DESAPARECIDO = ["Desaparecidos", "Pendientes"]

# Normalizaciones de nombre de entidad antes de tabular.
DIRECTORIO_INDICIOS_RENOMBRES = {"México": "Estado de México"}
DIRECTORIO_INDICIOS_SIN_ESTADO = "Sin información"

# Entidades que entran en la lámina, en el orden en que las pidió el área.
# Las que faltan (Aguascalientes, Chihuahua, Coahuila, Durango, Guanajuato,
# Jalisco, Nuevo León, Querétaro y "Nacido en el extranjero") quedan FUERA del
# conteo a propósito: el marcador cuenta sólo estas 24.
DIRECTORIO_INDICIOS_ESTADOS = [
    "Estado de México", "Tamaulipas", "Michoacán", "Sinaloa", "Guerrero",
    "Veracruz", "Ciudad de México", "Sonora", "Baja California", "Zacatecas",
    "Puebla", "Nayarit", "Chiapas", "Tabasco", "Hidalgo", "San Luis Potosí",
    "Quintana Roo", "Morelos", "Colima", "Baja California Sur", "Oaxaca",
    "Yucatán", "Tlaxcala", "Campeche",
]


# ─────────────────────────────────────────────────────────────────────────────
# RNIP y MJ (MJ + RIPS) · última lámina del reporte diario
# ─────────────────────────────────────────────────────────────────────────────
# Detenciones penitenciarias: personas del RNPDNO que fueron halladas en un
# Mandamiento Judicial (MJ) o en el Registro de Información Penitenciaria
# (RIPS). Es un insumo externo, igual que el directorio de indicios: NO pasa por
# el matching ni por `Slice`, porque su población no sale del RNPDNO ni de BANCI
# sino de este archivo. Lo único que se le pide al RNPDNO es el estatus vigente
# de cada FUB, y de ahí salen los cinco marcadores de la lámina:
#     {{reg_mr_min-max}}                 los registros del archivo completo
#     {{reg_mr_min-max_des}}             los que hoy siguen desaparecidos
#     {{reg_mr_min-max_loc}}             los que hoy están localizados
#     {{reg_mr_min-max_loc_cvid}}        de esos localizados, con vida
#     {{reg_mr_min-max_loc_svid}}        de esos localizados, sin vida
#     {{fha_mr_dia_mes_anio}}            la fecha de corte declarada abajo
# `min-max` no rebana nada: el archivo es una foto fija y se toma completo.
MJ_RIPS_DIR = INPUT_DIR / "mj"
MJ_RIPS_FILE = MJ_RIPS_DIR / "MJ y RIPS (1062).xlsx"

# Una hoja por fuente. La llave es lo que queda en la columna `tipo` del cruce,
# que es lo único que distingue de dónde vino cada registro una vez concatenados.
MJ_RIPS_SHEETS = {"MJ": "MJ UNICOS", "RIPS": "RIPS UNICOS"}

# Fecha de corte del archivo, en ISO. Sale del encabezado de
# `mj_rips_resumen.xlsx` ("Fecha: 20/08/2026"), que acompaña a este insumo.
# Alimenta `fha_mr_dia_mes_anio`; si llega un archivo nuevo, cambia aquí.
MJ_RIPS_FECHA_CORTE = "2026-08-20"

# Las dos hojas traen esquemas distintos (MJ 26 columnas, RIPS 18); estas siete
# son las que comparten y las únicas que se usan.
MJ_RIPS_COLUMN_MAPPING = {
    'fub':               ['FUB', 'fub'],
    'curp':              ['CURP', 'curp'],
    'fecha_hechos':      ['fechahechos', 'fecha_hechos'],
    'nombre':            ['Nombre', 'nombre'],
    'apellido_paterno':  ['Apellido Paterno', 'apellido_paterno'],
    'apellido_materno':  ['Apellido Materno', 'apellido_materno'],
    'estado':            ['ESTADO', 'estado'],
}

# Columnas que se le piden al universo RNPDNO para resolver el estatus de cada
# FUB. `estatus_loc` decide des/loc y las dos banderas parten a los localizados.
MJ_RIPS_RNPDNO_COLUMN_MAPPING = {
    'fub':         ['fub_rnpdno'],
    'estatus_loc': ['estatus_loc_derivada_rnpdno'],
    'is_cvid':     ['is_cvid_derivada_rnpdno'],
    'is_svid':     ['is_svid_derivada_rnpdno'],
}


# --- CORTE DE REFERENCIA · 25 DE MARZO DE 2026 -------------------------------
# Fotografía congelada del RNPDNO al 25/03/2026, entregada como Excel ya
# rebanado (un archivo por marcador). NO pasa por el pipeline: es la línea base
# contra la que se miden los marcadores de diferencia de la plantilla, del tipo
#     reg_rn_01ene06-max_des_sisf-reg_rn_25mar26_des_sisf
# que se leen como "cuánto creció el indicador desde el corte de marzo".
# El nombre de cada archivo ES el nombre del marcador que representa.
DATOS_MARZO_DIR = INPUT_DIR / "datos_marzo"
CORTE_25MAR26_FILES = {
    "reg_rn_25mar26_des_sisf":      DATOS_MARZO_DIR / "reg_rn_25mar26_des_sisf.xlsx",
    "reg_rn_25mar26_des_cisf_cind": DATOS_MARZO_DIR / "reg_rn_25mar26_des_cisf_cind.xlsx",
    "reg_rn_25mar26_des_cisf_sind": DATOS_MARZO_DIR / "reg_rn_25mar26_des_cisf_sind.xlsx",
}
# Columna identificadora sobre la que se cuentan los registros del corte.
CORTE_25MAR26_COL_ID = "fub"


# --- CORTE DE REFERENCIA · 1 DE JULIO DE 2026 --------------------------------
# Segunda fotografía congelada, con las mismas tres rebanadas que la de marzo y
# el mismo uso: la línea base de los marcadores
#     reg_rn_01ene06-max_des_sisf-reg_rn_01jul26_des_sisf
#     reg_rn_01ene06-max_des_sisf_ddes_v2 / _dloc_v2
# (`_v2` = el `_ddes`/`_dloc` de marzo, pero contra este corte). Salió de este
# mismo pipeline, así que sus columnas ya traen el sufijo de su fuente y el
# identificador llega como `fub_rnpdno`, no como `fub`.
DATOS_JULIO_DIR = INPUT_DIR / "datos_julio"
CORTE_01JUL26_FILES = {
    "reg_rn_01jul26_des_sisf":      DATOS_JULIO_DIR / "reg_rn_01jul26_des_sisf.xlsx",
    "reg_rn_01jul26_des_cisf_cind": DATOS_JULIO_DIR / "reg_rn_01jul26_des_cisf_cind.xlsx",
    "reg_rn_01jul26_des_cisf_sind": DATOS_JULIO_DIR / "reg_rn_01jul26_des_cisf_sind.xlsx",
}
CORTE_01JUL26_COL_ID = "fub_rnpdno"

# Todos los cortes de referencia, por marcador: (archivo, columna con el fub).
# Es lo que lee `src.utils.fubs_corte`. El nombre del marcador lleva la fecha
# del corte, así que los de un corte no chocan con los del otro.
CORTES_REFERENCIA = {
    **{m: (ruta, CORTE_25MAR26_COL_ID) for m, ruta in CORTE_25MAR26_FILES.items()},
    **{m: (ruta, CORTE_01JUL26_COL_ID) for m, ruta in CORTE_01JUL26_FILES.items()},
}


# Carpeta de los cortes del RNPDNO. El archivo que se lee NO se declara aquí: en
# modo local es RNPDNO_LOCAL_FILE (más abajo); en modo drive, el corte más reciente.
RNPDNO_MANUAL_DIR = INPUT_DIR / "rnpdno"


# --- EL PARQUET DEL RNPDNO SE RESUELVE POR FECHA, NO POR NOMBRE FIJO -----------
# El nombre lleva el corte en DDMMAAAA, y llega uno nuevo en cada entrega. En vez
# de editar esta línea en cada corte, se toma el de FECHA más alta que haya en
# input/rnpdno/. Se ordena por la fecha PARSEADA, no por el texto: alfabéticamente
# '18092026' va después de '01012027', y el corte real es el contrario.
#
# Lo llena 1_Procesamiento_ETL_RNPDNO bajándolo de Google Drive (ver src/drive.py).
RNPDNO_PARQUET_GLOB = "reporte_personas_completo_*.parquet"
RNPDNO_PARQUET_REGEX = re.compile(r"^reporte_personas_completo_(\d{2})(\d{2})(\d{4})\.parquet$")


def nombre_local_rnpdno(corte: date) -> str:
    """Nombre con el que se guarda un corte en input/rnpdno/.

    OJO: en Drive el archivo NO lleva fecha (se llama `RNPDNO_DRIVE_ARCHIVO` y se
    sobrescribe en cada entrega). La fecha se la pone src/drive.py al guardarlo, con
    el valor de `fecha_consulta` que trae el propio Parquet. Así el directorio local
    conserva el histórico y el nombre nunca miente sobre el contenido.
    """
    return f"reporte_personas_completo_{corte:%d%m%Y}.parquet"

# Último corte conocido. Sólo se usa cuando el directorio está vacío, para que el
# error diga qué archivo falta en lugar de reventar con un nombre en blanco.
RNPDNO_PARQUET_RESPALDO = RNPDNO_MANUAL_DIR / "reporte_personas_completo_18092026.parquet"


def fecha_corte_parquet_rnpdno(nombre) -> date | None:
    """Fecha de corte que declara el nombre del Parquet, o None si no es del patrón."""
    encontrado = RNPDNO_PARQUET_REGEX.match(getattr(nombre, "name", str(nombre)))
    if not encontrado:
        return None
    dia, mes, anio = (int(g) for g in encontrado.groups())
    try:
        return date(anio, mes, dia)
    except ValueError:
        # Un nombre con 8 dígitos que no son una fecha (p. ej. ..._99999999) no
        # es un corte válido y no debe ganarle al archivo bueno.
        return None


def parquet_rnpdno_mas_reciente(directorio=None) -> Path | None:
    """El Parquet del RNPDNO con el corte más reciente que haya EN ESE directorio.

    None cuando no hay ninguno. A propósito no cae al respaldo: quien pregunta por
    un directorio concreto necesita saber que ahí no hay nada, no recibir de vuelta
    un archivo de otra carpeta.
    """
    directorio = Path(directorio or RNPDNO_MANUAL_DIR)
    if not directorio.is_dir():
        return None
    candidatos = [
        (corte, ruta)
        for ruta in directorio.glob(RNPDNO_PARQUET_GLOB)
        if (corte := fecha_corte_parquet_rnpdno(ruta.name)) is not None
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda par: par[0])[1]


# MODO LOCAL: el archivo EXACTO que se lee cuando no se baja nada de Drive. A
# diferencia del modo "drive", aquí no se busca el más reciente ni se revisa la
# fecha del corte: se corre el archivo que diga esta línea, ys si no existe el
# notebook 1 se detiene.
# Puede ser el Parquet consolidado (.parquet) o el Excel de tres hojas (.xlsx): el
# formato se reconoce por la extensión (ver `formato_rnpdno`, abajo).
# Sobrescribir sin editar este archivo:  PIPELINE_RNPDNO_ARCHIVO=/ruta/al.parquet
RNPDNO_LOCAL_FILE = _ruta_declarada(
    "PIPELINE_RNPDNO_ARCHIVO",
    RNPDNO_MANUAL_DIR / "reporte_personas_completo_19102026.parquet",                      # Aquí se cambia el RNPDNO
    #RNPDNO_MANUAL_DIR / "reporte_personas_01072026.xlsx",                                 # Aquí se cambia el RNPDNO
)

# Esta es la que leen los notebooks y src/pipeline/exportacion_llaves.py. Se
# recalcula en cada `importlib.reload(config)`, que es justo lo que hace el
# notebook 1 después de bajar el archivo.
if RNPDNO_MODO_INSUMOS == "local":
    RNPDNO_MANUAL_FILE_2 = RNPDNO_LOCAL_FILE
else:
    RNPDNO_MANUAL_FILE_2 = parquet_rnpdno_mas_reciente() or RNPDNO_PARQUET_RESPALDO


# --- FORMATO DEL RNPDNO: PARQUET O EXCEL ---------------------------------------
# El RNPDNO llega en dos presentaciones con el mismo contenido:
#
#   "parquet"  Una sola tabla con las tres hojas apiladas. Es la que baja el modo
#              "drive"; las hojas se reconstruyen con `estatus` + `conidentidad`
#              (ver RNPDNO_ESTATUS_LOCALIZADAS, más abajo).
#   "excel"    El libro de siempre (reporte_personas_DDMMAAAA.xlsx), con las tres
#              hojas de SHEET_NAMES. Sólo se usa en modo "local".
#
# El notebook 1 lee cualquiera de los dos y deja la misma tabla para el resto del
# flujo; el notebook 7 devuelve la base con llave en el formato en que entró.
RNPDNO_FORMATOS = {".parquet": "parquet", ".xlsx": "excel"}


def formato_rnpdno(ruta) -> str:
    """'parquet' o 'excel', según la extensión del archivo del RNPDNO.

    Una extensión que no está en RNPDNO_FORMATOS se detiene aquí, con la ruta en el
    mensaje, en vez de fallar más adelante dentro de pandas.
    """
    sufijo = Path(ruta).suffix.lower()
    if sufijo not in RNPDNO_FORMATOS:
        raise ValueError(
            f"El archivo del RNPDNO {Path(ruta).name!r} no tiene un formato reconocido.\n"
            f"Extensiones aceptadas: {', '.join(RNPDNO_FORMATOS)}."
        )
    return RNPDNO_FORMATOS[sufijo]


# --- DESCARGA AUTOMÁTICA DEL RNPDNO DESDE GOOGLE DRIVE ------------------------
# Todo este bloque sólo aplica en modo "drive" (ver MODO_INSUMOS arriba). En modo
# "local" no se lee nada de aquí: ni carpeta, ni credenciales, ni tolerancia.
#
# Las credenciales NO están aquí ni en ningún archivo versionado: viven en
# `.secrets/` (ya cargado arriba con el bloque de MODO_INSUMOS), que git ignora y que
# los asistentes de IA tienen bloqueado por `.claude/settings.json`. Este bloque sólo
# conoce las RUTAS. Ver docs/9_credenciales_google_drive.md.

# Carpeta de Drive con el Parquet del RNPDNO. Acepta el id pelón o la URL completa;
# src.drive.extraer_id_carpeta se encarga.
RNPDNO_DRIVE_FOLDER_ID = os.getenv("GDRIVE_RNPDNO_FOLDER_ID", "").strip()

# Nombre EXACTO del archivo dentro de esa carpeta. Se exige exacto y no por patrón
# porque ahí conviven varios Parquet (desaparecidas, localizadas, pendientes) y sólo
# el consolidado sirve de insumo.
RNPDNO_DRIVE_ARCHIVO = (
    os.getenv("GDRIVE_RNPDNO_ARCHIVO", "").strip() or "reporte_personas_completo.parquet"
)

def _ruta_secreta(variable: str, por_defecto: str) -> Path:
    """Ruta a un archivo de credenciales: relativa a la raíz del proyecto o absoluta."""
    valor = os.getenv(variable, "").strip()
    if not valor:
        return SECRETS_DIR / por_defecto
    ruta = Path(valor)
    return ruta if ruta.is_absolute() else BASE_DIR / ruta


# OAuth de usuario: la descarga corre con la cuenta de quien ejecuta el notebook.
# `oauth_client.json` es el ID de cliente de escritorio que se descarga de Google
# Cloud; `oauth_token.json` lo escribe el propio código tras el primer consentimiento
# y se refresca solo. No hay cuenta de servicio: la organización tiene activada
# `iam.disableServiceAccountKeyCreation` y no deja generar la llave JSON.
RNPDNO_DRIVE_OAUTH_CLIENTE = _ruta_secreta("GDRIVE_OAUTH_CLIENT_JSON", "oauth_client.json")
RNPDNO_DRIVE_OAUTH_TOKEN = _ruta_secreta("GDRIVE_OAUTH_TOKEN_JSON", "oauth_token.json")

# Se conserva por compatibilidad con el código y la documentación que preguntaban por
# esta bandera. Hoy es una lectura del modo: apagar la descarga es correr en local.
RNPDNO_DRIVE_HABILITADO = RNPDNO_MODO_INSUMOS == "drive"

# Antigüedad máxima, en días, del corte que el pipeline acepta correr. 0 = sólo el
# corte del día. Existe para que una caída de Drive no se convierta en un reporte
# calculado en silencio sobre datos viejos: si el Parquet que hay no es del día, el
# proceso se detiene en vez de continuar. Súbelo a 1 si el RNPDNO publica con un día
# de retraso, o pon un número grande para reprocesar un corte antiguo a propósito.
#
# Se lee SÓLO de aquí. Antes salía de GDRIVE_RNPDNO_DIAS_TOLERANCIA en
# .secrets/drive.env, y esa variable le ganaba en silencio a cualquier cambio hecho en
# este archivo; si todavía está en tu drive.env, ya no hace nada.
RNPDNO_DIAS_TOLERANCIA = 1    # Aquí se cambia la tolerancia del RNPDNO


# --- DESCARGA AUTOMÁTICA DE LA PUI DESDE GOOGLE DRIVE -------------------------
# También sólo aplica en modo "drive". Misma mecánica que el RNPDNO y las mismas credenciales de `.secrets/`, pero otra
# carpeta y otro formato: aquí llega un .zip diario que hay que descomprimir.
#
# El id se lee de GDRIVE_PUI_FOLDER_ID en `.secrets/drive.env`, igual que el del RNPDNO.
# No es un secreto, pero tampoco va en el código: el repo se comparte fuera de la
# organización y la carpeta es interna. Si falta, la descarga se detiene y lo dice.
PUI_DRIVE_FOLDER_ID = os.getenv("GDRIVE_PUI_FOLDER_ID", "").strip()

# Igual que RNPDNO_DRIVE_HABILITADO: lectura del modo, no un interruptor aparte.
PUI_DRIVE_HABILITADO = PUI_MODO_INSUMOS == "drive"

# Tolerancia PROPIA, separada de la del RNPDNO a propósito: las dos fuentes deben
# llegar diario, pero las suben áreas distintas y no siempre fallan el mismo día.
# Con una sola variable, aflojar una aflojaría la otra sin querer.
#
# Igual que la del RNPDNO, se lee SÓLO de aquí: GDRIVE_PUI_DIAS_TOLERANCIA en
# .secrets/drive.env ya no hace nada.
PUI_DIAS_TOLERANCIA = 1    # Aquí se cambia la tolerancia de la PUI

# Hojas esperadas en el Excel de RNPDNO
SHEET_NAMES = {
    "PENDIENTES": "ACTUALIZACION_PENDIENTE",
    "LOCALIZADAS": "LOCALIZADAS",
    "DESAPARECIDAS": "DESAPARECIDAS"
}

# Reconstrucción de esas hojas desde el Parquet consolidado (RNPDNO_MANUAL_FILE_2).
# El Parquet apila las tres hojas en una sola tabla y NO guarda de cuál vino cada
# fila, pero `estatus` + `conidentidad` las separan sin ambigüedad:
#
#   LOCALIZADAS    → estatus en RNPDNO_ESTATUS_LOCALIZADAS
#   DESAPARECIDAS  → el resto, con conidentidad = true
#   PENDIENTES     → el resto, con conidentidad = false
#
# Verificado fila por fila contra reporte_personas_18092026.xlsx: 0 discrepancias
# en 409,241 registros (PENDIENTES 37,390 | LOCALIZADAS 277,818 | DESAPARECIDAS 94,033).
# `estatus` NO basta por sí solo: DESAPARECIDA y NO LOCALIZADA aparecen en las dos
# hojas de no localizados.
RNPDNO_ESTATUS_LOCALIZADAS = ["LOCALIZADA CON VIDA", "LOCALIZADA SIN VIDA"]

# Claves que el Parquet entrega como texto (el Excel también: el notebook 1 lo lee
# como texto para que las dos fuentes den la misma tabla). La copia `_rnpdno` las
# conserva así; la columna de trabajo del notebook 1 pasa a número (y de ella, las
# derivadas).
RNPDNO_PARQUET_COLS_NUMERICAS = ["idestado", "idmunicipio", "idestadonacimiento_vic"]

# Columnas que el Excel nombra distinto que el Parquet. Los dos lectores las
# renombran a como vienen en el Parquet, para que la copia `_rnpdno` se llame igual
# venga de donde venga (`curp_vic_rnpdno`, `expedientes_rnpdno`, que leen los
# motores y las derivadas). Sólo cambia el nombre; el valor queda intacto.
# Se compara sin distinguir mayúsculas y también contra el nombre destino: el propio
# Parquet ha traído el expediente como `expediente`, `Expediente` o `Expedientes`
# según el corte, y los tres quedan como `Expedientes`.
RNPDNO_EXCEL_A_PARQUET = {"curp_victima": "curp_vic", "expediente": "Expedientes"}
# --- DEFINICIONES Y MAPEOS DE COLUMNAS ---
# Estructura: 'Nombre_Estandar_Interno': ['Posible_Nombre_1', 'Posible_Nombre_2', ...]
# ESTA ES LA ESTRUCTURA PRINCIPAL PARA RNPDNO (La "Fuente de la Verdad"):
RNPDNO_COLUMN_MAPPING = {
    # Identidad
    'fub': ['fub', 'folio_fub', 'folio_rnpdno', 'folio'],
    'nombre_vic': ['nombre_vic', 'nombre'],
    'primerapellido_vic': ['primerapellido_vic', 'primer_apellido'],
    'segundoapellido_vic': ['segundoapellido_vic', 'segundo_apellido'],
    'curp_vic': ['curp_vic', 'curp', 'curp_victima'],
    'sexo': ['sexo'],
    'fechanacimiento': ['fechanacimiento', 'fecha_nacimiento', 'fha_nac'],
    'idestadonacimiento_vic': ['idestadonacimiento_vic'],
    
    # Ubicación (Fiscalía/Entidad)
    'idestado': ['idestado', 'cve_ent', 'estado_id', 'entidad_id'],
    'idmunicipio': ['idmunicipio'],
    
    # Fechas
    'fechahechos': ['fechahechos', 'fecha_hechos', 'fha_de_hchos'],
    'fechapercato': ['fechapercato', 'fecha_percato'],
    'fechacaptura': ['fechacaptura', 'fecha_captura'],
    # Fecha en que se localizó a la persona. Sólo la traen los registros
    # LOCALIZADA CON/SIN VIDA: en DESAPARECIDA y NO LOCALIZADA viene vacía por
    # definición, no por un fallo del ETL. El Parquet de origen marca ese hueco
    # con cadena vacía, que el paso de STR_NA_VALUES del notebook 1 vuelve NA
    # antes de parsear la fecha.
    'fechalocaliza': ['fechalocaliza', 'fecha_localiza', 'fecha_localizacion'],
    
    # Estatus y Clasificación
    'estatus': ['estatus'],
    'delitolocalizacion': ['delitolocalizacion'],
    
    # Administrativo
    'expediente': ['expediente', 'Expediente', 'expedientes', 'Expedientes'],
    'dependencia_origen': ['dependencia_origen', 'dependencia', 'autoridad'],
    'fecha_consulta': ['fecha_consulta', 'fechaconsulta']
}

# --- CONFIGURACIÓN DE SALIDA ---
# Directorio raíz para resultados
# (Se eliminó la creación automática de la carpeta RNPDNO)


# --- FILTRO DE ENTIDAD EN LOS NOTEBOOKS ETL (1 y 2) ---
# ⚠️ DEBE PERMANECER EN None PARA EL PIPELINE DE INDICADORES.
#
# Esta variable sólo la leen 1_Procesamiento_ETL_RNPDNO y 2_Procesamiento_ETL_BANCI.
# Si se activa, los Parquet de origen quedan filtrados por entidad y el universo
# dejaría de ser nacional, que es la premisa de la arquitectura actual:
# la entidad es una DIMENSIÓN DE REBANADA, no un filtro previo al matching.
#
# Para una PPT estatal NO se toca esto. Se rebana:
#     Slice("rn", "01oct24-max", estatus="des", estado=17)
#     Settings.desde_perfil("estatal").con(estado=17)
#
# `src/pipeline/carga.py` aborta con un mensaje explícito si detecta que está activa.
ESTADO = None

# True: las presentaciones filtran y rotulan con el estado extraído de la dependencia.
# False: conservan la entidad basada directamente en idestado del RNPDNO.
USAR_ESTADO_EXTRAIDO_EN_PRESENTACIONES = True

# Relación entre la clave de la entidad (dos dígitos numéricos) y el nombre de la entidad de forma correcta
# Obtenidos del catalogo_municipios_inegi.csv
ENTIDADES = {
    1: 'Aguascalientes',
    2: 'Baja California',
    3: 'Baja California Sur',
    4: 'Campeche',
    5: 'Coahuila',
    6: 'Colima',
    7: 'Chiapas',
    8: 'Chihuahua',
    9: 'Ciudad de México',
    10: 'Durango',
    11: 'Guanajuato',
    12: 'Guerrero',
    13: 'Hidalgo',
    14: 'Jalisco',
    15: 'México',
    16: 'Michoacán',
    17: 'Morelos',
    18: 'Nayarit',
    19: 'Nuevo León',
    20: 'Oaxaca',
    21: 'Puebla',
    22: 'Querétaro',
    23: 'Quintana Roo',
    24: 'San Luis Potosí',
    25: 'Sinaloa',
    26: 'Sonora',
    27: 'Tabasco',
    28: 'Tamaulipas',
    29: 'Tlaxcala',
    30: 'Veracruz',
    31: 'Yucatán',
    32: 'Zacatecas',
    33: 'Nacido en el Extranjero'
}





# Modalidad para clasificar registros "con carpeta" y "sin carpeta"
# 1: Modalidad antigua (usa RNPDNO_REGEX_CARPETA general)
# 2: Modalidad nueva (usa regex específico por entidad federativa)
# 3: Como la 2, pero con CATALOGO_REGEX_CI_POR_ENTIDAD_2 y, en Oaxaca, una segunda capa:
#    las siglas del folio deben estar en NOMENCLATURAS_OAXACA
# 4: Unión de la 2 y la 3 con CATALOGO_REGEX_CI_POR_ENTIDAD_3, sin la capa de siglas de Oaxaca
# 5: Como la 4, valida contra la entidad del RNPDNO O estado_final_nuevo; basta que uno coincida
MODALIDAD_CLASIFICACION_CARPETA = 5

# False: clasifica con `idestado_derivada_rnpdno` (estado del RNPDNO).
# True: usa `idestado_final_nuevo`, la clave numérica del estado extraído que se
# presenta como `estado_final_nuevo`. La modalidad 5 siempre evalúa ambos estados.
USAR_ESTADO_EXTRAIDO_PARA_CLASIFICAR_CARPETA = True

# Validación manual de carpeta, encima de MODALIDAD_CLASIFICACION_CARPETA:
# True  → valen las carpetas que valida la modalidad MÁS todos los registros de los
#         archivos de CARPETAS_MANUALES_DIR, aunque su folio no pase el regex de la
#         modalidad o venga vacío.
# False → sólo valen las que valida la modalidad; los archivos se ignoran.
# La revisión sólo puede AGREGAR carpetas válidas, nunca quitarlas.
MODALIDAD_MANUAL_CLASIFICACION_CARPETA = True

# Revisiones manuales de carpeta. Se leen TODOS los archivos de la carpeta con una
# extensión de CARPETAS_MANUALES_EXTENSIONES: para sumar una revisión nueva basta con
# dejarla ahí. El formato es Parquet —se lee sólo la columna del FUB—; el Excel se
# sigue aceptando para que ninguna revisión vieja quede fuera. Cuenta todo FUB de la
# columna CARPETAS_MANUALES_COL_FUB, diga lo que diga el resto del archivo (el
# dictamen "Se repite" o "Vacío" también cuenta). Se compara sin espacios y en
# mayúsculas, así que un FUB repetido en dos archivos cuenta una vez.
CARPETAS_MANUALES_DIR = INPUT_DIR / "carpetas_manuales"
CARPETAS_MANUALES_COL_FUB = "fub_rnpdno"
CARPETAS_MANUALES_EXTENSIONES = (".parquet", ".xlsx")


def archivos_carpetas_manuales(directorio=None) -> list[Path]:
    """Los archivos de revisión manual de carpeta, en orden. Omite los `~$…` que deja
    Excel abierto."""
    d = Path(directorio or CARPETAS_MANUALES_DIR)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.suffix.lower() in CARPETAS_MANUALES_EXTENSIONES
                  and not p.name.startswith("~$"))

# Columnas posibles para identificar 'dependencia' en archivos de confrontas

# Regex para identificar si un expediente tiene Carpeta de Investigación (CI/CDI/AP) - Modalidad 1
RNPDNO_REGEX_CARPETA = r'\bAP\b|\b(CI|CDI)\b'

# Catálogo de Regex para identificar Carpetas de Investigación por entidad federativa - Modalidad 2
# Nota: Se incluyen entidades federales (FED/Fiscalía General) con sus propios patrones
CATALOGO_REGEX_CI_POR_ENTIDAD = {
    "Fiscalía General de la República": r"^(?i)FED(?:[-/])[A-Z]+(?:[-/])[A-Z]+(?:(?:[-/])[A-Z]+)*(?:[-/])\d{7}(?:[-/])\d{4}$",
    "Fiscalía General (BANCI MATCH)": r"^(?i)FED(?:[-/])[A-Z]+(?:[-/])[A-Z]+(?:(?:[-/])[A-Z]+)*(?:[-/])\d{7}(?:[-/])\d{4}$",
    "Aguascalientes": r"^CI(?:[-/])[A-Za-z]{3}(?:[-/])\d{5}(?:[-/])(0[1-9]|1[0-2])(?:[-/])\d{2}$",
    "Baja California": r"^(?i)\d(?:[-/]?\d{2})(?:[-/]?\d{3})(?:[-/]?\d{4})(?:[-/]?\d{5})$",
    "Baja California Sur": r"^(?i)[a-z]{3}(?:[-/]?[1-9]\d*)(?:[-/]?\d{4})(?:[-/]?nuc)$",
    "Coahuila": r"^(?i)[a-z0-9]{1,5}(?:[-/]?[a-z0-9]{3})(?:[-/]?[a-z0-9]{5,10})(?:[-/]?\d{4})$",
    "Colima": r"^(?i)nsjp/[a-z]{3}/(?:ci|ch)/[a-z0-9]{1,50} [0-9]{1,3}/\d{4}$",
    "Chiapas": r"^(?i)\d{4}(?:[-/]?\d{3})(?:[-/]?\d{4})(?:[-/]?\d{4,5})$",
    "Chihuahua": r"^(?i)\d{2}(?:[-/]?\d{4})(?:[-/]?\d{7})$",
    "Ciudad de México": r"^(?i)(?:ci|ae)[-/](?:f[a-z0-9]+|e)[-/][a-z0-9]+(?:[/-][a-z0-9]+)*[-/]ui[-/]?\d+(?:\s)?(?:[-/]?(?:s|c)[-/]d)[-/]\d{5}[-/](0[1-9]|1[0-2])[-/]\d{4}$",
    "Durango": r"^(?i)(?:[a-z]{3}(?:[-/]?\d{4})(?:[-/]?\d{6,})|\d{2,3}(?:[-/]?\d{4})(?:[-/]?\d+)|(?:cdi|ci)(?:[-/][a-z0-9]+){3,7})$",
    "Guanajuato": r"^(?i)\d+(?:[-/]?\d{4})$",
    "Guerrero": r"^(?i)\d{2}(?:[-/]?\d{2})(?:[-/]?\d{3})(?:[-/]?\d{2})(?:[-/]?\d{5})(?:[-/]?\d{6})$",
    "Hidalgo": r"^(?i)(?:[a-z0-9]+(?:[-/]?\d{4})(?:[-/]?\d+)|fed[-/]hgo[-/]?[a-z]+(?:[-/]?\d+)(?:[-/]?\d{4}))$",
    "Jalisco": r"^(?i)[a-z0-9-]+(?:[-/]?[a-z0-9-]+)(?:[-/]?\d{4})$",
    "México": r"^(?i)(?:(?:FED(?:[-/])[A-Z]+(?:[-/])[A-Z]+(?:(?:[-/])[A-Z0-9-]+)*(?:[-/])\d{7}(?:[-/])\d{4})|(?:[a-z0-9]{3}(?:[-/]?[a-z0-9]{3})(?:[-/]?(?:[a-z0-9]{3}[-/]?\d{3}[-/]?\d{6}|\d{2}[-/]?[a-z0-9]{3}[-/]?\d{3}[-/]?\d{5}))[-/]?\d{2}[-/]?(0[1-9]|1[0-2])))$",
    "Morelos": r"^(?i)[a-z0-9]{2,10}(?:[-/]?\d+)(?:[-/]?\d{4})$",
    "Nuevo León": r"^(?i)(?:fgjnl[-/]?\d{6}[-/]?\d{4}|\d+[-/]?\d{4})$",
    "Oaxaca": r"^(?i)\d+(?:[-/]?[a-z0-9-]+)(?:[-/]?\d{4})$",
    "Querétaro":  r"^(?i)ci(?:[-/]?[a-z]{3})(?:[-/]?\d+)(?:[-/]?\d{4})$",
    "San Luis Potosí": r"^(?i)(?:cdi|csc)(?:[-/]?fge)(?:[-/]?(?:i|ii|iii|iv|v|vi))(?:[-/]?d(?:0[1-9]|1[0-3]))(?:[-/]?\d{5})(?:[-/]?\d{2})$",
    "Sinaloa": r"^(?i)(?:[a-z]{3,6}(?:[-/]?[a-z0-9]{2,10})(?:[-/]?\d{3,})(?:[-/]?\d{4})(?:[-/]?[a-z]{1,3})?|[a-z0-9]{3}(?:[-/]?\d+)(?:[-/]?\d{4}))$",
    "Sonora": r"^(?i)[a-z0-9]{1,5}(?:[-/]?[a-z0-9]{1,5})(?:[-/]?[a-z0-9]{1,5})(?:[-/]?\d{1,4})(?:[-/]?[a-z0-9]{1,5})(?:[-/]?\d+)$",
    "Tabasco": r"^(?i)ci[-/][a-z0-9_]{2,20}(?:[-/][a-z0-9_]{1,20}){0,3}[-/]?\d+[-/]?\d{4}$",
    "Tamaulipas": r"^(?i)fgjt(?:[-/][a-z0-9]+){2,5}[-/]\d+[-/]\d{4}$",
    "Tlaxcala": r"^(?i)fg(?:[-/]?(?:ui|ai))(?:[-/]?(?:apiz|ixt|tlax|huam|calp|spm))(?:[-/]?[a-z0-9]+)(?:[-/]?\d+)(?:[-/]?\d{4})$",
    "Veracruz": r"^(?i)(?:[a-z0-9]{1,6}(?:[-/]?\d+)(?:[-/]?\d{2,4})|(?:[a-z0-9]{1,12}[-/])+(?:feadpd|fedfp|fepd|feiddfpdcp|fedfpdcp|feiddfp|fedfpm)(?:[-/][a-z0-9]{1,12})*[-/]\d+[-/]\d{2,4})$",
    "Yucatán": r"^(?i)(?:[a-z0-9]{2}(?:[-/]?\d{6})(?:[-/]?\d{4})|fge(?:[-/]?[a-z0-9._áéíóúñ-]+)(?:[-/]?[a-z0-9.-]+)(?:[-/]?\d{4}))$",
    "Zacatecas": r"^(?i)(?:fgjez(?:[-/]?[a-z0-9_-]+)(?:[-/]?[a-z0-9_-]+)(?:[-/]?\d+)(?:[-/]?\d{4}[-/]?(?:0?[1-9]|1[0-2]))|\d+[-/]?\d{4}[-/]?(?:0?[1-9]|1[0-2]))$",
    "Campeche": r"^(?i)ci(?:[-/]?\d{1,3})(?:[-/]?\d{4})(?:[-/]?[1-9]\d*)$",
    "Nayarit": r"^(?i)nay(?:[-/]?[a-z0-9]{2,5})(?:[-/]?m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))(?:[-/]?(?:ci|rh))(?:[-/]?\d{5})(?:[-/]?\d{4})$",
    "Michoacán": r"^(?i)[a-z0-9]{2,10}(?:[-/]?\d+)(?:[-/]?\d{4})$",
    "Puebla": r"\bAP\b|\b(CI|CDI)\b",
    "Quintana Roo": r"(?i)(?:\bAP\b|\bCI\b|\bCDI\b|\bFGE\s*[-/_]*\s*QROO\b)"
}

# Prefijos con que abren los folios de CI de Baja California Sur (en R: `nomenclaturas_bcs`).
NOMENCLATURAS_BCS = ["LPZ", "TS", "PLN", "LBR", "SGO", "SJC", "CSL", "CST",
                     "INS", "SCL", "LOR", "MGE", "SRL", "GNO", "VIZ", "BT"]

# Prefijo de los folios de Coahuila: CI o APP, con puntos opcionales (en R: `prefijo_coah`).
PREFIJO_COAH = r"(?:c\.?i\.?|a\.?p\.?p\.?)"


CATALOGO_REGEX_CI_POR_ENTIDAD_2 = {
    "Fiscalía General de la República": r"^(?i)FED(?:[-/])[A-Z]+(?:[-/])[A-Z]+(?:(?:[-/])[A-Z]+)*(?:[-/])\d{7}(?:[-/])\d{4}$",
    "Fiscalía General (BANCI MATCH)": r"^(?i)FED(?:[-/])[A-Z]+(?:[-/])[A-Z]+(?:(?:[-/])[A-Z]+)*(?:[-/])\d{7}(?:[-/])\d{4}$",
    "Aguascalientes": r"^(?:CI|CH|ACTC)[-/][A-Za-z]{3}[-/]\d{5}[-/](0[1-9]|1[0-2])[-/]\d{2}$",
    "Baja California": r"^(?i)\d{4}[-/]\d{4}[-/]\d{5}(?:[-/](?:AP|AC|NAC|NUC))?$",
    "Baja California Sur": rf"^(?i)(?:{'|'.join(NOMENCLATURAS_BCS)})(?:[-/]?[1-9]\d*)(?:[-/]?[a-z0-9]+)(?:[-/]?(?:nuc|\d{{4}}))$",
    "Chiapas": r"^(?i)C\.I\.\d{4}[-/]\d{3}[-/]\d{4}[-/]\d{4,5}$",
    "Chihuahua": r"^(?i)\d{2}(?:[-/]?\d{4})(?:[-/]?\d{7})$",
    "Ciudad de México": r"^(?i)(?:ci|ae)[-/](?:e[-/])?f[a-z0-9]+[-/][a-z0-9]+(?:[/-][a-z0-9]+)*[-/]ui[-/]?\d+(?:\s)?(?:[-/]?(?:s|c)[-/]d)[-/]\d{1,5}[-/](0[1-9]|1[0-2])[-/]\d{4}$",
    "Campeche": r"^(?i)(?:ci|ac)(?:[-/]?\d{1,3})(?:[-/]?\d{4})(?:[-/]?[1-9]\d*)$",
    "Coahuila": rf"(?i)^{PREFIJO_COAH}(?:[-/]?{PREFIJO_COAH})?[-/]?\d+[-/](?:\d{{4}}|[a-z]+)(?:[-/](?:ulpnl|atpdt?)[-/]\d{{4}})?$",
    "Colima": r"^(?i)nsjp/[a-z]{3}/(?:ci|ch)/[a-z0-9]{1,50}[ /][0-9]{1,3}/\d{4}$",
    "Durango": r"^(?i)c\.?(?:d\.?)?i\.?/fge/r[0-9]{1,2}(?:/[a-z]{3})?/\d+/\d{4}$",
    "Guanajuato": r"^(?i)\d+(?:[-/]?\d{4})$",
    "Guerrero": r"^(?i)(?:\d{14}(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])\d{2}|[a-z]{3}/[a-z]{2}/\d{2}/\d{3}/\d{4})$",
    "Hidalgo": r"^(?i)(?:(?:0[1-9]|1\d|20)(?:[-/]?\d{4})(?:[-/]?\d+)|fed[-/]hgo[-/]?[a-z]+(?:[-/]?\d+)(?:[-/]?\d{4}))$",
    "Jalisco": r"^(?i)[0-9-]+(?:[-/]?[a-z0-9-]+)(?:[-/]?\d{4})$",
    "México": r"^(?i)(?:(?:FED(?:[-/])[A-Z]+(?:[-/])[A-Z]+(?:(?:[-/])[A-Z0-9-]+)*(?:[-/])\d{7}(?:[-/])\d{4})|(?:[a-z0-9]{3}(?:[-/]?[a-z0-9]{3})(?:[-/]?(?:[a-z0-9]{3}[-/]?\d{2,3}[-/]?\d{6}|\d{2}[-/]?[a-z0-9]{3}[-/]?\d{2,3}[-/]?\d{5}))[-/]?\d{2}[-/]?(0[1-9]|1[0-2])))$",
    "Morelos": r"^(?i)[a-z0-9]+(?:-[a-z0-9]+)?[-/]\d+[-/]\d{4}$",
    "Nuevo León": r"^(?i)[a-z0-9]+[-/]?\d{4}$",
    "Oaxaca": r"^(?i)\d+(?:[-/]?[a-z0-9-]+)(?:[-/]?\d{4})$",
    "Querétaro": r"^(?i)(?:ci[-/]?(?:[a-z]{3}[-/]?)?\d+[-/]?\d{4}|[1-4][-/]\d+[-/]\d+[-/]\d+[-/]\d{2}|[ivxlc]+[-/]?\d+[-/]?\d{4})$",
    "San Luis Potosí": r"^(?i)(?:cdi|csc)(?:[-/]?fge)(?:[-/]?(?:i|ii|iii|iv|v|vi))(?:[-/]?d(?:0[1-9]|1[0-3]))(?:[-/]?\d{5})(?:[-/]?\d{2})$",
    "Sinaloa": r"^(?i)(?:[a-z]{3,6}(?:[-/]?[a-z0-9]{2,10})(?:[-/]?\d{3,})(?:[-/]?\d{4})(?:[-/]?[a-z]{1,3})?|[a-z0-9]{3}(?:[-/]?\d+)(?:[-/]?\d{4}))$",
    "Sonora": r"^(?i)[a-z0-9]{1,5}(?:[-/]?[a-z0-9]{1,5})(?:[-/]?[a-z0-9]{1,5})(?:[-/]?\d{1,4})(?:[-/]?[a-z0-9]{1,5})(?:[-/]?\d{1,2})[-/]\d{4}$",
    "Tabasco": r"^(?i)ci[-/][a-z0-9_]{2,20}(?:[-/][a-z0-9_]{1,20}){0,3}[-/]?\d+[-/]?\d{4}$",
    "Tamaulipas": r"^(?i)(?:fgjt(?:[-/][a-z0-9]+){2,5}[-/]\d+[-/]\d{4}|\d{2}[-/]?\d{2}[-/]?\d{3}[-/]?\d+[-/]?\d{4})$",
    "Tlaxcala": r"^C\.I\.\s?FG-[A-Za-z0-9]+[-/][0-9]+[-/][0-9]{4}$",
    "Veracruz": r"^(?i)(?:[a-z0-9]{1,6}(?:[-/]?\d+)(?:[-/]?\d{2,4})|(?:[a-z0-9]{1,12}[-/])+(?:feadpd|fedfp|fepd|feiddfpdcp|fedfpdcp|feiddfp|fedfpm)(?:[-/][a-z0-9]{1,12})*[-/]\d+[-/]\d{2,4})$",
    "Yucatán": r"^(?i)(?:[a-z0-9]{2}(?:[-/]?\d{3,6})(?:[-/]?\d{4})|fge(?:[-/]?[a-z0-9.áéíóúñ -]+)(?:[-/]?[a-z0-9._ -]+)(?:[-/]?\d{4}))$",
    "Zacatecas": r"^(?i)(?:fgjez(?:[-/]?[a-z0-9_-]+)(?:[-/]?[a-z0-9_-]+)(?:[-/]?\d+)(?:[-/]?\d{4}[-/]?(?:0?[1-9]|1[0-2]))|\d+[-/]?\d{4}[-/]?(?:0?[1-9]|1[0-2])|av[-/]?\d+[-/]?\d{4}[-/]?(?:0?[1-9]|1[0-2]))$",
    "Nayarit": r"^(?i)nay(?:[-/]?[a-z0-9]{2,5})(?:[-/]?m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))(?:[-/]?(?:ci|rh))(?:[-/]?\d{5,7})(?:[-/]?\d{4})$",
    "Michoacán": r"^[A-Za-z0-9]{2,10}[-/]?[0-9]+(?:[-/]?[0-9]+)?[-/]?[0-9]{4}$",
    "Puebla": r"^FGEP/CDI/[A-Za-z0-9.\- ]+/[A-Za-z0-9.\- ]+/[0-9]+/[0-9]{4}$",
    "Quintana Roo": r"^(?i)(?:FGE/QROO|CI)(?:/[A-Z0-9]+)+/?$"
}


def _unir_regex(*patrones: str) -> str:
    """Une patrones en una alternancia: el folio pasa si cumple cualquiera.

    Cada patrón se envuelve en su propio grupo y su flag global (`^(?i)...`) se
    vuelve local (`(?i:^...)`), para que la sensibilidad a mayúsculas de uno no
    alcance a los demás. Los repetidos se quedan una sola vez.
    """
    alternativas = []
    for patron in dict.fromkeys(p for p in patrones if p):
        flags = "".join(re.findall(r"\(\?([aiLmsux]+)\)", patron))
        cuerpo = re.sub(r"\(\?[aiLmsux]+\)", "", patron)
        alternativas.append(f"(?{''.join(sorted(set(flags)))}:{cuerpo})")
    return "|".join(alternativas)


# Unión de los dos catálogos anteriores: un folio pasa si cumple la regla de
# CATALOGO_REGEX_CI_POR_ENTIDAD_2 o la de CATALOGO_REGEX_CI_POR_ENTIDAD. Así se ganan
# los formatos nuevos del _2 sin perder ningún folio que ya pasaba con el original.
CATALOGO_REGEX_CI_POR_ENTIDAD_3 = {
    entidad: _unir_regex(CATALOGO_REGEX_CI_POR_ENTIDAD_2.get(entidad),
                         CATALOGO_REGEX_CI_POR_ENTIDAD.get(entidad))
    for entidad in {**CATALOGO_REGEX_CI_POR_ENTIDAD_2, **CATALOGO_REGEX_CI_POR_ENTIDAD}
}

# Segunda capa de la modalidad 3, sólo para Oaxaca: su patrón acepta casi cualquier
# número-texto-año, así que de los folios que lo pasan se extraen las siglas —lo que hay
# entre el consecutivo inicial y el año final— y deben existir en NOMENCLATURAS_OAXACA.
REGEX_SIGLAS_CI_OAXACA = r"^\d+[-/]?(.+?)[-/]?\d{4}$"

# Siglas válidas de Oaxaca con su agencia o unidad (en R: `catalogo_nomenclatura_oaxaca_todos`).
# Sólo se compara la nomenclatura; la agencia queda como referencia. Algunas siglas se
# repiten con otra descripción (ETLA, AYUTLA, OAXACA…), igual que en R.
CATALOGO_NOMENCLATURA_OAXACA = [
    ("UEDF",           "UNIDAD ESPECIAL EN DESAPARICION FORZADA"),
    ("SAVJRSC",        "MESA DE PERSONAS DESAPARECIDAS"),
    ("ADNOL",          "UNIDAD DE ATENCION A PERSONAS NO LOCALIZADAS"),
    ("RDNOL",          "UNIDAD DE ATENCION A PERSONAS NO LOCALIZADAS"),
    ("DNOL",           "UNIDAD DE ATENCION A PERSONAS NO LOCALIZADAS"),
    ("ACATLAN",        "ACATLAN DE PEREZ FIGUEROA"),
    ("AYUTLA",         "SAN PEDRO SAN PABLO AYUTLA MIXES"),
    ("FIXTLAN",        "FISCALIA DE IXTLAN DE JUAREZ"),
    ("FTFM",           "FISCALIA DE TEOTITLAN DE FLORES MAGON"),
    ("FCUICA",         "FISCALIA DE SAN JUAN BAUTISTA CUICATLAN"),
    ("FVA",            "FISCALIA DE VILLA ALTA"),
    ("FZAC",           "FISCALIA DE ZACATEPEC MIXE"),
    ("VGCR",           "VICEFISCALIA GENERAL DE CONTROL REGIONAL"),
    ("FAYUTLA",        "FISCALIA DE AYUTLA, MIXE"),
    ("FHJ",            "FISCALIA DE HUAUTLA DE JIMENEZ"),
    ("CATL",           "COORDINACION DE APOYO TECNICO Y LITIGACION"),
    ("CHAHUITES",      "CHAHUITES"),
    ("CODDI-OCOTLAN",  "OCOTLAN DE MORELOS - CODDI"),
    ("CODDI-TUXTEPEC", "SAN JUAN BAUTISTA TUXTEPEC - CODDI"),
    ("CODDI-ZAACHILA", "VILLA DE ZAACHILA - CODDI"),
    ("COIXTLAHUACA",   "SAN JUAN BAUTISTA COIXTLAHUACA"),
    ("COSOLAPA",       "SAN JOSE COSOLAPA"),
    ("CUICATLAN",      "SAN JUAN BAUTISTA CUICATLAN"),
    ("FRG",            "FISCALIA DE RIO GRANDE"),
    ("SPP",            "SAN PEDRO POCHUTLA"),
    ("FPE",            "FISCALIA DE PUERTO ESCONDIDO"),
    ("FSPN",           "FISCALIA DE SANTIAGO PINOTEPA NACIONAL"),
    ("PN",             "PINOTEPA NACIONAL"),
    ("FSJ.",           "FISCALIA DE SANTIAGO JAMITELPEC"),
    ("PE",             "PUERTO ESCONDIDO"),
    ("FSBCH",          "FISCALIA DE SANTA CRUZ HUATULCO"),
    ("FSPP",           "FISCALIA DE SAN PEDRO POCHUTLA"),
    ("DATS",           "DIRECCION DE ASUNTOS DE TRASCENDENCIA SOCIAL"),
    ("EJUTLA",         "EJUTLA DE CRESPO"),
    ("ETLA",           "ETLA"),
    ("FADO",           "FISCALIA ESPECIALIZADA EN JUSTICIA PARA ADOLESCENTES"),
    ("FADO-HUAJUAPAN", "HUAJUAPAN DE LEON - FADO"),
    ("FADO-JUCHITAN",  "JUCHITAN DE ZARAGOZA - FADO"),
    ("FADO-PUERTO",    "PUERTO ESCONDIDO - FADO"),
    ("FAMI-IXTEPEC",   "IXTEPEC - FAMI"),
    ("FACAT",          "FISCALIA DE ACATLAN DE PEREZ FIGUEROA"),
    ("FTDAI",          "FISCALIA DE ALTO IMPACTO CUENCA"),
    ("FTUXT",          "FISCALIA DE TRAMITE TUXTEPEC"),
    ("FTUXM",          "FISCALIA DE DELITOS CONTRA LA MUJER POR RAZON DE GENERO CUENCA"),
    ("FMLOM",          "FISCALIA DE MARIA LOMBARDO DEL CASO"),
    ("FLOMA",          "FISCALIA DE LOMA BONITA CUENCA"),
    ("FAMI-MATIAS",    "MATIAS ROMERO AVENDANO - FAMI"),
    ("FAMI-YAUTEPEC",  "SAN CARLOS YAUTEPEC - FAMI"),
    ("FDPE",           "FISCALIA CONTRA LA DESAPARICION DE PERSONAS"),
    ("FMUJ-TLAXIACO",  "HEROICA CIUDAD DE TLAXIACO - FMUJ"),
    ("HUAJUAPAN",      "HUAJUAPAN DE LEON"),
    ("HUATULCO",       "SANTA CRUZ HUATULCO"),
    ("HUAUTLA",        "HUAUTLA DE JIMENEZ"),
    ("IXTEPEC",        "IXTEPEC"),
    ("ZN",             "SANTO DOMINGO ZANATEPEC"),
    ("JU",             "JUCHITAN DE ZARAGOZA"),
    ("TH",             "TEHUANTEPEC"),
    ("MR",             "MATIAS ROMERO"),
    ("CH.",            "FISCALIA MIGRANTE CHAHUITES"),
    ("SC.",            "SALINA CRUZ"),
    ("IXTLAN",         "IXTLAN DE JUAREZ"),
    ("JAMILTEPEC",     "SANTIAGO JAMITELPEC"),
    ("JUCHITAN",       "JUCHITAN DE ZARAGOZA"),
    ("JUQUILA",        "SANTA CATARINA JUQUILA"),
    ("JUXTLAHUACA",    "SANTIAGO JUXTLAHUACA"),
    ("LOMA",           "LOMA BONITA"),
    ("LOMBARDO",       "MARIA LOMBARDO DE CASO"),
    ("MATIAS",         "MATIAS ROMERO AVENDANO"),
    ("MIAHUATLAN",     "MIAHUATLAN DE PORFIRIO DIAZ"),
    ("NOCHIXTLAN",     "ASUNCION NOCHIXTLAN"),
    ("OAXACA",         "OAXACA DE JUAREZ"),
    ("OCOTLAN",        "OCOTLAN DE MORELOS"),
    ("HL",             "HUAJUAPAN DE LEON"),
    ("TX",             "FISCALIA DE TLAXIACO"),
    ("FSJ",            "FISCALIA DE SANTIAGO JUXTLAHUACA"),
    ("PG",             "PUTLA DE GUERRERO"),
    ("DNOLMIXTECA-TX", "DNOL TLAXIACO"),
    ("PINOTEPA",       "SANTIAGO PINOTEPA NACIONAL"),
    ("POCHUTLA",       "SAN PEDRO POCHUTLA"),
    ("PUERTO",         "PUERTO ESCONDIDO"),
    ("PUTLA",          "PUTLA DE VILLA DE GUERRERO"),
    ("RIO",            "RIO GRANDE"),
    ("SALINA",         "SALINA CRUZ"),
    ("SILACAYOAPAM",   "SILACAYOAPAM"),
    ("SOLA",           "SOLA DE VEGA"),
    ("SOYALTEPEC",     "SAN MIGUEL SOYALTEPEC"),
    ("TEHUANTEPEC",    "SANTO DOMINGO TEHUANTEPEC"),
    ("FOM",            "FISCALIA OCOTLAN DE MORELOS"),
    ("ETLA",           "ETLA."),
    ("SC",             "SECTOR CENTRAL"),
    ("CR",             "CRUZ ROJA"),
    ("FEC",            "FISCALIA EJUTLA DE CRESPO"),
    ("ZIMATLAN",       "ZIMATLAN DE ALVAREZ..."),
    ("SAVJ",           "SUBPROC ATN A VIC JR Y SC"),
    ("FZIM",           "FISCALIA ZIMATLAN DE ALVAREZ"),
    ("AYUTLA",         "SAN PEDRO Y SAN PABLO AYUTLA."),
    ("EJUTLA",         "EJUTLA DE CRESPO."),
    ("FTM",            "FISCALIA TLACOLULA DE MATAMOROS"),
    ("OCOTLAN",        "OCOTLAN DE MORELOS."),
    ("PME",            "POLICIA MINISTERIAL DEL E"),
    ("OAXACA",         "OAXACA ZONA CENTRO."),
    ("FETLA",          "FISCALIA ETLA"),
    ("ZAACHILA",       "ZAACHILA."),
    ("CH",             "CENTRO HISTORICO"),
    ("FZAA",           "FISCALIA ZAACHILA"),
    ("TLACOLULA",      "TLACOLULA."),
    ("TEOTITLAN",      "TEOTITLAN DE FLORES MAGON"),
    ("TEPOSCOLULA",    "SAN PEDRO Y SAN PABLO TEPOSCOLULA"),
    ("TLACOLULA",      "TLACOLULA DE MATAMOROS"),
    ("TLAXIACO",       "HEROICA CIUDAD DE TLAXIACO"),
    ("TUXTEPEC",       "SAN JUAN BAUTISTA TUXTEPEC"),
    ("UDNA",           "UNIDAD DE DELITOS CONTRA NINOS, NINAS Y ADOLESCENTES"),
    ("UECS",           "UNIDAD ESPECIALIZADA EN EL COMBATE AL SECUESTRO Y EXTORSION"),
    ("UEIH",           "UNIDAD ESPECIALIZADA EN LA INVESTIGACION DE HOMICIDIOS"),
    ("UELE",           "UNIDAD ESPECIALIZADA PARA LA ATENCION DE DELITOS COMETIDOS EN CONTRA DE LA LIBERTAD DE EXPRESION"),
    ("UNNA",           "UNIDAD OPERATIVA ESPECIALIZADA PARA NINAS, NINOS Y ADOLESCENTES VICTIMAS DEL DELITO"),
    ("DS",             "DELITOS SEXUALES"),
    ("UNOL",           "UNIDAD DE BUSQUEDA DE PERSONAS NO LOCALIZADAS"),
    ("AM.",            "ATENCION A MENORESS"),
    ("VALLE-NACIONAL", "SAN JUAN BAUTISTA VALLE NACIONAL"),
    ("VILLA",          "SAN IDELFONSO VILLA ALTA"),
    ("YAUTEPEC",       "SAN CARLOS YAUTEPEC"),
    ("FCDO",           "FISCALIA DE COMBATE A LA DELINCUENCIA ORGANIZADA"),
    ("FEDAI",          "FISCALIA ESPECIALIZADA PARA LA ATENCION A DELITOS DE ALTO IMPACTO"),
    ("SADAI",          "SUBPROC PARA LA ATENCION DE DELITOS DE ALTO IMPACTO"),
    ("ZAACHILA",       "VILLA DE ZAACHILA"),
    ("FEADAI",         "FISCALIA ESPECIALIZADA PARA LA ATENCION A DELITOS DE ALTO IMPACTO (6 SIGLAS)"),
    ("ZACATEPEC",      "SANTIAGO ZACATEPEC MIXES"),
    ("ZANATEPEC",      "SANTO DOMINGO ZANATEPEC"),
    ("FIDTS",          "FISCALIA DE INVESTIGACION EN DELITOS DE TRASCENDENCIA SOCIAL"),
    ("ZIMATLAN",       "ZIMATLAN DE ALVAREZ"),
]

NOMENCLATURAS_OAXACA = [nomenclatura for nomenclatura, _ in CATALOGO_NOMENCLATURA_OAXACA]



RESULTADOS_INDICADORES_DIR = OUTPUT_DIR / "Resultados_4_Generacion_Indicadores"
RESULTADOS_INDICADORES_DIR.mkdir(parents=True, exist_ok=True)

INDICADORES_DESAPARECIDOS_FILE = RESULTADOS_INDICADORES_DIR / "indicadores_selectos_desaparecidos.csv"
