import re
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import sys
import os
from pathlib import Path

def validar_columnas(df: pd.DataFrame, columnas_esperadas: list, nombre_fuente: str):
    """
    Verifica que las columnas esperadas existan en el DataFrame.
    Si falta alguna columna, interrumpe el proceso arrojando un error detallado.
    """
    faltantes = [col for col in columnas_esperadas if col not in df.columns]
    if faltantes:
        mensaje_error = (
            f"❌ ERROR CRÍTICO: La base de datos '{nombre_fuente}' no contiene las "
            f"siguientes columnas requeridas: {faltantes}. "
            "Es probable que hayan cambiado de nombre en el archivo de origen."
        )
        print(mensaje_error)
        raise ValueError(mensaje_error)
    print(f"✅ Validación de columnas completada para '{nombre_fuente}'. Todas las columnas esperadas están presentes.")

# Agregamos el directorio raíz al path para poder importar config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

def es_curp_valida_vectorizado(series: pd.Series) -> pd.Series:
    """
    Valida una serie de CURPs aplicando las reglas de negocio definidas en config.py.
    Retorna una Serie booleana (True si es válida, False si no).
    """
    # 1. Longitud exacta de 18 caracteres
    # (Manejamos NA como False o strings vacíos como False)
    cond_longitud = series.str.len() == 18

    # 2. Regex de formato general (4 letras + 6 números + H/M)
    cond_formato = series.str.contains(config.CURP_REGEX_FORMAT, regex=True, na=False, flags=re.IGNORECASE)

    # 3. Regex de homoclave (3 letras + 2 caracteres finales)
    cond_homoclave = series.str.contains(config.CURP_REGEX_HOMOCLAVE, regex=True, na=False, flags=re.IGNORECASE)

    # 4. Código de estado válido (caracteres 12 y 13, índices 11:13 en 0-based index)
    # Extraemos el substring de la posición 12 y 13 (indices 11 y 12)
    codigo_estado = series.str.slice(11, 13).str.upper()
    cond_estado = codigo_estado.isin(config.VALID_STATE_CODES)

    # Combinar todas las condiciones
    es_valida = cond_longitud & cond_formato & cond_homoclave & cond_estado
    
    return es_valida

def limpiar_curp(series: pd.Series) -> pd.Series:
    """CURP lista para validar o comparar: sin espacios, en mayúsculas y con los
    vacíos como nulo.

    Es la única limpieza de CURP del proyecto: la usan el ETL de BANCI para su
    bandera de validez y el motor estándar para comparar BANCI contra el RNPDNO.
    """
    return (
        series.astype(str)
        .str.replace(r"\s+", "", regex=True)
        .str.upper()
        .replace(["NAN", "NONE", ""], np.nan)
    )

def verificar_consistencia_duplicados(df: pd.DataFrame, key_col: str, cols_to_check: list) -> bool:
    """
    Verifica si los registros duplicados validos por 'key_col' contienen información idéntica 
    en las columnas 'cols_to_check'.
    
    Retorna True si los duplicados son consistentes (mismo info), False si hay conflictos.
    Lancea una excepción con detalles si hay inconsistencias para detener el flujo.
    """
    # Filtramos duplicados en la llave
    duplicados = df[df.duplicated(subset=key_col, keep=False)].copy()
    
    if duplicados.empty:
        return True # No hay duplicados, por ende es consistente
        
    # Agrupamos por FUB y contamos valores únicos en las columnas de interés concatenadas
    # O más fácil: numero de unique rows por grupo
    
    # Seleccionamos solo las columnas de interés implicadas en la identidad de la persona
    # Aseguramos que existan en el df
    cols_existentes = [c for c in cols_to_check if c in df.columns]
    
    # Agrupamos y contamos combinaciones únicas
    inconsistencias = duplicados.groupby(key_col)[cols_existentes].nunique().max(axis=1)
    
    # Si algún FUB tiene > 1 version de datos en alguna columna
    fubs_conflictivos = inconsistencias[inconsistencias > 1]
    
    if not fubs_conflictivos.empty:
        errores = fubs_conflictivos.index.tolist()[:5] # Mostramos solo los primeros 5
        mensaje = f"Inconsistencia encontrada en {len(fubs_conflictivos)} FUBs duplicados: {errores}..."
        print(f"❌ {mensaje}")
        # En el script original esto hace un stop()
        raise ValueError(mensaje)
        
    return True

def deduplicar_por_fub(df: pd.DataFrame, key_col: str = 'fub') -> pd.DataFrame:
    """
    Mantiene solo el primer registro único por FUB.
    Se asume que la verificación de consistencia ya pasó.
    """
    n_antes = len(df)
    df_dedup = df.drop_duplicates(subset=key_col, keep='first')
    n_despues = len(df_dedup)
    
    if n_antes != n_despues:
        print(f"  ℹ️ Se eliminaron {n_antes - n_despues} registros duplicados (idénticos).")
    
    return df_dedup

def cargar_y_consolidar_curps(cruces_dir: Path) -> pd.DataFrame:
    """
    Lee multiples archivos auxiliares de CURP (CSV/XLSX), valida format y consolida.
    """
    dfs_aux = []
    
    for filename in config.RENAPO_FILES:
        # Aseguramos que filename sea un objeto Path
        file_path = Path(filename)
        
        if not file_path.exists():
            print(f"  ⚠️ Advertencia: Archivo auxiliar no encontrado: {file_path}")
            continue
            
        try:
            # Lectura según extensión
            if str(file_path).endswith('.csv'):
                df = pd.read_csv(file_path, encoding='utf-8')
            else:
                df = pd.read_excel(file_path)
            
            # Normalizar columnas para encontrar 'fub' y 'curp'
            # Convertimos a minúsculas para búsqueda flexible
            df.columns = df.columns.str.lower()
            
            # Selección flexible de columnas
            col_fub = next((c for c in df.columns if 'fub' in c), None) # Contiene 'fub'
            col_curp = next((c for c in df.columns if 'curp_obtenida' in c or 'curp' in c), None)
            
            if col_fub and col_curp:
                df_sel = df[[col_fub, col_curp]].copy()
                df_sel.columns = ['fub', 'curp_obtenida'] # Renombrar estándar
                
                # Validación de CURP (Reutilizamos la funció vectorizada existente)
                df_sel['es_valida'] = es_curp_valida_vectorizado(df_sel['curp_obtenida'].astype(str))
                
                # Filtrar solo válidas
                df_validas = df_sel[df_sel['es_valida']].drop(columns=['es_valida'])
                
                dfs_aux.append(df_validas)
                print(f"  ✅ {filename}: {len(df_validas)} CURPs válidas recuperadas.")
            else:
                print(f"  ⚠️ Formato desconocido en {filename}. Columnas encontradas: {df.columns.tolist()}")

        except Exception as e:
            print(f"  ❌ Error leyendo {filename}: {e}")

    if not dfs_aux:
        print("  ⚠️ No se cargaron CURPs auxiliares. Se retorna DataFrame vacío.")
        return pd.DataFrame(columns=['fub', 'curp_obtenida'])
    
    # Concatenar todos
    consolidado = pd.concat(dfs_aux, ignore_index=True)
    
    # Deduplicar por FUB (quedarse con el primero encontrado)
    consolidado = consolidado.drop_duplicates(subset='fub', keep='first')
    
    print(f"  📊 Total consolidado RENAPO: {len(consolidado)} registros únicos.")
    return consolidado

def segmentar_bases(dfs_imputados: dict, dfs_originales: dict) -> dict:
    """
    Separa los registros en dos categorías:
    1. Base CON CURP: Registros que ya cuentan con CURP válida (o imputada).
    2. Base SIN CURP: Registros que no tienen CURP, excluyendo los que ya están en la Base CON CURP.
    """
    result = {
        'con_curp': {},
        'sin_curp': {}
    }
    
    # 1. Base Final CON CURP (Filtrar los que SÍ tienen CURP)
    # Según R: map(~ filter(.x, !is.na(curp_vic)))
    fubs_con_curp = set()
    
    for key, df in dfs_imputados.items():
        if 'curp_vic_valida_derivada_rnpdno' in df.columns:
            # CRITERIO ESTRICTO: Solo aceptamos registros con CURP VÁLIDA
            # Los que tengan CURP pero sea inválida no entrarán aquí (fubs_con_curp), 
            # y por lo tanto caerán en la base SIN CURP (Pendientes) en el siguiente paso al no ser excluidos.
            # La validez la calculó imputar_curps; aquí sólo se lee.
            mask_con_curp = df['curp_vic_valida_derivada_rnpdno']
            
            df_con = df[mask_con_curp].copy()
            result['con_curp'][key] = df_con
            
            # Recolectamos FUBs
            fubs_con_curp.update(df_con['fub'].astype(str).unique())
        else:
            # Si no tiene columna curp_vic, se asume que no va a 'con_curp' 
            # (ej. Localizadas podrían quedarse tal cual o no entrar aquí)
            pass

    print(f"  ℹ️ FUBs identificados con CURP válida/imputada: {len(fubs_con_curp)}")

    # 2. Base Final SIN CURP (Filtro Anti-Join)
    # Usamos dfs_imputados que ya limpios de duplicados y con nombres normalizados.
    
    # Hojas candidatas a tener pendientes (todas menos LOCALIZADAS)
    sheets_sin_curp = [k for k in dfs_imputados.keys() if k != 'LOCALIZADAS']
    
    for key, df in dfs_imputados.items():
        if key in sheets_sin_curp:
            # Convertir fub a string para comparar
            df['fub_str'] = df['fub'].astype(str)
            
            # Filtramos los que NO están en fubs_con_curp
            df_sin = df[~df['fub_str'].isin(fubs_con_curp)].copy()
            df_sin = df_sin.drop(columns=['fub_str'])
            
            result['sin_curp'][key] = df_sin
            
    # Validación R: "no debe quedar ninguna CURP válida en sin_curp"
    n_errores = 0
    for key, df in result['sin_curp'].items():
        if 'curp_vic_valida_derivada_rnpdno' in df.columns:
            validas = df['curp_vic_valida_derivada_rnpdno']
            if validas.any():
                print(f"  ❌ ERROR: Hay {validas.sum()} CURPs válidas en la base SIN CURP ({key}).")
                n_errores += 1
                
    if n_errores == 0:
        print("  ✅ Validación correcta: La base SIN CURP no contiene registros con CURP válida.")
        
    return result

def imputar_curps(df_original: pd.DataFrame, df_renapo: pd.DataFrame) -> pd.DataFrame:
    """
    Imputa CURPs en df_original usando df_renapo cuando la original es inválida
    y la de RENAPO es válida.
    Mantiene la original 'curp_vic' intacta y escribe el resultado en
    'curp_vic_derivada_rnpdno', con su bandera 'curp_vic_valida_derivada_rnpdno'.
    """
    df = df_original.copy()
    
    # Asegurar que existan las columnas
    if 'curp_vic' not in df.columns:
        print("  ⚠️ La columna 'curp_vic' no existe. Saltando imputación.")
        return df

    # 1. Evaluar estado inicial
    df['curp_valida_inicial'] = es_curp_valida_vectorizado(df['curp_vic'].astype(str))
    n_validas_antes = df['curp_valida_inicial'].sum()
    
    # 2. Unir (Left Join) con RENAPO
    # Convertimos FUB a string para asegurar match
    df['fub'] = df['fub'].astype(str)
    df_renapo['fub'] = df_renapo['fub'].astype(str)
    
    df_merged = pd.merge(df, df_renapo, on='fub', how='left')
    
    # 3. Lógica de Imputación Vectorizada
    # Condición: (Original INVÁLIDA) Y (Renapo EXISTE/NO NA)
    # Nota: Ya filtramos renapo para que solo tenga válidas en la función anterior,
    # así que si existe match, asumimos que es válida.
    
    cond_imputar = (~df_merged['curp_valida_inicial']) & (df_merged['curp_obtenida'].notna())
    
    # --- curp_vic y su copia curp_vic_rnpdno quedan intactas; la imputada va aparte ---
    df_merged['curp_vic_derivada_rnpdno'] = df_merged['curp_vic']
    df_merged.loc[cond_imputar, 'curp_vic_derivada_rnpdno'] = df_merged.loc[cond_imputar, 'curp_obtenida']

    # 4. Evaluación Final
    df_merged['curp_vic_valida_derivada_rnpdno'] = es_curp_valida_vectorizado(
        df_merged['curp_vic_derivada_rnpdno'].astype(str))
    n_validas_despues = df_merged['curp_vic_valida_derivada_rnpdno'].sum()
    
    ganancia = n_validas_despues - n_validas_antes
    
    n_registros = len(df_merged)
    n_invalidas = n_registros - n_validas_despues
    
    print(f"  📈 Resultado Imputación:")
    print(f"     - Total Registros: {n_registros}")
    print(f"     - Válidas Antes:   {n_validas_antes}")
    print(f"     - Válidas Después: {n_validas_despues}")
    print(f"     - Sin CURP Válida: {n_invalidas}")
    print(f"     - Ganancia Neta:   +{ganancia} CURPs recuperadas.")
    
    # Limpieza de columnas auxiliares
    cols_drop = ['curp_obtenida', 'curp_valida_inicial']
    df_final = df_merged.drop(columns=[c for c in cols_drop if c in df_merged.columns])
    
    return df_final

# ─── CLASIFICACIÓN DE CARPETA DE INVESTIGACIÓN ───────────────────────────────
# Implementación única de `config.MODALIDAD_CLASIFICACION_CARPETA`, compartida
# por el ETL (1_Procesamiento_ETL_RNPDNO) y por el pipeline de indicadores
# (src/pipeline/carga.py) para que ambos clasifiquen igual.

def normalizar_regex(patron: str) -> str:
    """Iza los flags globales —`(?i)`, `(?s)`…— al inicio del patrón.

    Varios patrones de `CATALOGO_REGEX_CI_POR_ENTIDAD` los llevan después del
    ancla `^` (`^(?i)\\d{2}...`). Python 3.11+ rechaza eso con
    "global flags not at the start of the expression", así que 29 de los 32
    patrones no compilan con el módulo `re`.

    Hoy no revientan sólo porque las columnas del Parquet son Arrow-backed y
    pandas despacha a RE2, que sí lo tolera; con dtype `object` el mismo código
    fallaría. Izar los flags produce resultados idénticos en ambos motores y
    elimina esa dependencia del backend.
    """
    flags = re.findall(r"\(\?([aiLmsux]+)\)", patron)
    if not flags:
        return patron
    cuerpo = re.sub(r"\(\?[aiLmsux]+\)", "", patron)
    return f"(?{''.join(sorted(set(''.join(flags))))}){cuerpo}"


def _siglas_validas_oaxaca() -> set:
    """`config.NOMENCLATURAS_OAXACA` en mayúsculas y sin espacios, como lo compara R.

    Se detiene si el catálogo falta: sin él, todos los folios de Oaxaca quedarían
    "Sin carpeta" sin que nada lo avisara.
    """
    siglas = getattr(config, "NOMENCLATURAS_OAXACA", None)
    if siglas is None or len(siglas) == 0:
        raise ValueError(
            "La modalidad 3 valida las siglas de los folios de Oaxaca contra "
            "`config.NOMENCLATURAS_OAXACA`, que está vacío. Llénalo o usa la modalidad 2."
        )
    return {str(s).strip().upper() for s in siglas if pd.notna(s) and str(s).strip()}


def clasificar_carpeta(expediente: pd.Series,
                       cve_entidad: pd.Series = None,
                       modalidad: int = None,
                       cve_entidad_alternativa: pd.Series = None) -> pd.Series:
    """Marca qué expedientes corresponden a una Carpeta de Investigación.

    modalidad 1 → `config.RNPDNO_REGEX_CARPETA`, un solo regex para todo el país.
    modalidad 2 → `config.CATALOGO_REGEX_CI_POR_ENTIDAD`, un regex por entidad;
                  requiere `cve_entidad` (clave INEGI numérica).
    modalidad 3 → `config.CATALOGO_REGEX_CI_POR_ENTIDAD_2`, igual que la 2, más una
                  segunda capa en Oaxaca: las siglas del folio deben estar en
                  `config.NOMENCLATURAS_OAXACA`.
    modalidad 4 → `config.CATALOGO_REGEX_CI_POR_ENTIDAD_3`, la unión de los catálogos
                  de la 2 y la 3: pasa todo lo que pasa en cualquiera de ellas. No
                  aplica la capa de siglas de Oaxaca, que quitaría folios de la 2.
    modalidad 5 → usa el catálogo de la modalidad 4 con ambas claves de entidad;
                  basta con que el folio pase para cualquiera de ellas.

    Si `modalidad` es None se toma de `config.MODALIDAD_CLASIFICACION_CARPETA`.

    Devuelve una Serie booleana (True = con carpeta).
    """
    if modalidad is None:
        modalidad = getattr(config, "MODALIDAD_CLASIFICACION_CARPETA", 1)

    if modalidad == 5:
        claves = [clave for clave in (cve_entidad, cve_entidad_alternativa)
                  if clave is not None]
        if not claves:
            raise ValueError(
                "La modalidad 5 necesita al menos una clave de entidad INEGI."
            )
        valido = pd.Series(False, index=expediente.index)
        for clave in claves:
            valido |= clasificar_carpeta(expediente, clave, modalidad=4)
        return valido

    # Los patrones están anclados con ^...$; quita espacios de borde y reduce los
    # espacios internos repetidos, que aparecen en folios válidos capturados.
    exp = (expediente.fillna("").astype(str).str.strip()
           .str.replace(r"\s+", " ", regex=True).str.upper())

    if modalidad == 1:
        return exp.str.contains(normalizar_regex(config.RNPDNO_REGEX_CARPETA),
                                regex=True, na=False)

    if modalidad not in (2, 3, 4):
        raise ValueError(
            f"MODALIDAD_CLASIFICACION_CARPETA = {modalidad!r} no es válida. Use 1, 2, 3, 4 o 5."
        )

    if cve_entidad is None:
        raise ValueError(
            f"La modalidad {modalidad} clasifica con un regex por entidad y necesita "
            "`cve_entidad` (clave INEGI). Pásala o cambia a modalidad 1."
        )

    if modalidad == 2:
        catalogo, siglas_oaxaca = config.CATALOGO_REGEX_CI_POR_ENTIDAD, None
    elif modalidad == 3:
        catalogo, siglas_oaxaca = config.CATALOGO_REGEX_CI_POR_ENTIDAD_2, _siglas_validas_oaxaca()
    else:
        catalogo, siglas_oaxaca = config.CATALOGO_REGEX_CI_POR_ENTIDAD_3, None

    claves = pd.to_numeric(cve_entidad, errors="coerce")
    mask = pd.Series(False, index=exp.index)
    sin_patron = []
    for cve, nombre in config.ENTIDADES.items():
        patron = catalogo.get(nombre)
        sel = claves == cve
        if not sel.any():
            continue
        if not patron:
            sin_patron.append(nombre)
            continue
        valido = exp.loc[sel].str.contains(normalizar_regex(patron), regex=True, na=False)
        if nombre == "Oaxaca" and siglas_oaxaca is not None:
            # Segunda capa: sólo puede quitar carpetas, nunca agregarlas. Un folio sin
            # siglas extraíbles queda en NaN y `isin` lo marca False.
            siglas = exp.loc[sel].str.extract(config.REGEX_SIGLAS_CI_OAXACA, expand=False)
            valido = valido & siglas.isin(siglas_oaxaca)
        mask.loc[sel] = valido
    if sin_patron:
        print(f"  ⚠️ Sin regex de carpeta en el catálogo (se marcan 'Sin carpeta'): {sin_patron}")
    return mask


def _columna_fub_manual(ruta: Path, col_fub: str) -> pd.Series:
    """La columna de FUB de un archivo de revisión manual, según su extensión.

    Del Parquet se lee sólo esa columna; el Excel no lo permite y se lee entero.
    Se detiene si falta la columna: ignorar el archivo en silencio dejaría sin
    carpeta a registros que la revisión dio por válidos.
    """
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".parquet":
        if col_fub in pq.read_schema(ruta).names:
            return pd.read_parquet(ruta, columns=[col_fub])[col_fub]
    else:
        df = pd.read_excel(ruta, dtype=str)
        if col_fub in df.columns:
            return df[col_fub]
    raise ValueError(f"{ruta.name} no trae la columna {col_fub!r} "
                     "(config.CARPETAS_MANUALES_COL_FUB).")


def fubs_carpeta_valida_manual(archivos=None) -> set:
    """FUBs que la revisión manual da por carpeta válida: todos los de la columna
    `config.CARPETAS_MANUALES_COL_FUB` de cada archivo (Parquet o Excel) de
    `config.CARPETAS_MANUALES_DIR` (o de `archivos`), sin espacios y en mayúsculas.
    """
    if archivos is None:
        archivos = config.archivos_carpetas_manuales()
    col_fub = config.CARPETAS_MANUALES_COL_FUB

    fubs = set()
    for ruta in archivos:
        serie = _columna_fub_manual(ruta, col_fub).dropna().astype(str).str.strip().str.upper()
        fubs |= set(serie[serie != ""])
    return fubs


def carpeta_validada_manual(fub: pd.Series, activa: bool = None,
                            verbose: bool = True) -> pd.Series:
    """Marca los registros que la revisión manual da por carpeta válida.

    Es la capa de `config.MODALIDAD_MANUAL_CLASIFICACION_CARPETA`: se suma (OR) a
    `clasificar_carpeta`, así que sólo puede agregar carpetas válidas, nunca quitarlas.
    Si `activa` es None se toma de `config.MODALIDAD_MANUAL_CLASIFICACION_CARPETA`;
    apagada, devuelve todo False sin leer los archivos.

    Devuelve una Serie booleana (True = carpeta válida por revisión manual).
    """
    if activa is None:
        activa = getattr(config, "MODALIDAD_MANUAL_CLASIFICACION_CARPETA", False)
    if not activa:
        return pd.Series(False, index=fub.index)

    archivos = config.archivos_carpetas_manuales()
    # Lo que haya en la carpeta con otra extensión NO se lee: se avisa, porque la
    # carpeta promete que todo lo que trae cuenta como carpeta válida.
    directorio = Path(config.CARPETAS_MANUALES_DIR)
    ignorados = sorted(p.name for p in directorio.iterdir()
                       if p.is_file() and p not in archivos
                       and not p.name.startswith(("~$", "."))) if directorio.is_dir() else []
    if ignorados:
        print(f"  ⚠️ {len(ignorados)} archivo(s) de {directorio.name}/ no se leen: su "
              f"extensión no está en config.CARPETAS_MANUALES_EXTENSIONES: {', '.join(ignorados)}")
    fubs = fubs_carpeta_valida_manual(archivos)
    if not fubs:
        print("  ⚠️ MODALIDAD_MANUAL_CLASIFICACION_CARPETA está activa pero "
              f"{config.CARPETAS_MANUALES_DIR} no trae ningún FUB: "
              "no se agrega ninguna carpeta.")
        return pd.Series(False, index=fub.index)

    claves = fub.fillna("").astype(str).str.strip().str.upper()
    mask = claves.isin(fubs)
    faltan = fubs - set(claves[mask])
    if verbose:
        print(f"  📋 Revisión manual de carpeta: {len(fubs):,} FUBs en "
              f"{len(archivos)} archivo(s); {len(fubs) - len(faltan):,} están en el RNPDNO.")
    if faltan:
        muestra = ", ".join(sorted(faltan)[:5])
        print(f"  ⚠️ {len(faltan):,} FUBs de la revisión manual no están en el "
              f"RNPDNO: {muestra}{' …' if len(faltan) > 5 else ''}")
    return mask
