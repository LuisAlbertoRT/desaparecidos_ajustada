import pandas as pd
import numpy as np
import sys
import os
import re

# Agregamos el directorio raíz al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from src.utils import standardize_columns

# --- Mapeo Dinámico de Columnas desde config ---
def get_col_key(mapping, alias, default):
    return next((k for k, v in mapping.items() if str(alias).lower() in [str(x).lower() for x in v] or k == default), default)

# BANCI columns
col_b_nombres = get_col_key(config.BANCI_COLUMN_MAPPING, 'nombres', 'nombres')
col_b_primer_apellido = get_col_key(config.BANCI_COLUMN_MAPPING, 'primer_apellido', 'primer_apellido')
col_b_segundo_apellido = get_col_key(config.BANCI_COLUMN_MAPPING, 'segundo_apellido', 'segundo_apellido')
col_b_fha_nac = get_col_key(config.BANCI_COLUMN_MAPPING, 'fecha_nacimiento', 'fha_nac')
col_b_fecha_inicio = get_col_key(config.BANCI_COLUMN_MAPPING, 'fecha_inicio', 'fha_de_ini')
col_b_entidad = get_col_key(config.BANCI_COLUMN_MAPPING, 'entidad', 'entidad')

# RNPDNO columns
col_r_nombre_vic = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'nombre_vic', 'nombre_vic')
col_r_primerapellido_vic = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'primer_apellido', 'primerapellido_vic')
col_r_segundoapellido_vic = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'segundo_apellido', 'segundoapellido_vic')
col_r_curp_vic = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'curp', 'curp_vic')
col_r_fechacaptura = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'fecha_captura', 'fechacaptura')
col_r_fechahechos = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'fecha_hechos', 'fechahechos')
col_r_fechapercato = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'fecha_percato', 'fechapercato')
col_r_fechanacimiento = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'fecha_nacimiento', 'fechanacimiento')
col_r_idestado = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'idestado', 'idestado')
col_r_fub = get_col_key(config.RNPDNO_COLUMN_MAPPING, 'fub', 'fub')

col_b_fecha_hechos = get_col_key(config.BANCI_COLUMN_MAPPING, "fecha_hechos", "fha_de_hchos")

def normalizar_texto(texto):
    """
    Elimina acentos, pasa a mayúsculas y quita espacios extra.
    Replica logicamente 'reemplazo_acentos' de R.
    AHORA VECTORIZADA (ACEPTA SERIES O SCALARS).
    """
    if isinstance(texto, pd.Series):
        # Versión vectorizada optimizada
        s = texto.fillna('').astype(str).str.upper()
        
        # Tabla de traducción optimizada (str.translate)
        # 1. Mapeo de acentos (Á->A, é->E, etc.)
        # Nota: Pandas .str.translate usa dict de enteros (ord), no str.maketrans directo a veces
        # Pero podemos aplicar map o translate a nivel string.
        
        # Opción más rápida en pandas moderno:
        # Usar replace con regex para todo lo que no sea 'Ñ' (R behavior)
        
        # Map manual eficiente
        replacements = {
            "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U"
        }
        # Aplicamos reemplazos. Para pocos caracteres, replace encadenado es aceptable
        # Ojo: str.replace de pandas usa regex por defecto en versiones viejas, 
        # en nuevas regex=False es mas rapido si es literal, o regex=True.
        # Dado que son caracteres simples:
        for a, b in replacements.items():
            s = s.str.replace(a, b, regex=False)
            
        # Quitar espacios extra y trim
        s = s.str.replace(r'\s+', ' ', regex=True).str.strip()
        
        # Restaurar NaNs originales si se requiere, pero aquí ' ' es vacío
        mask_nan = texto.isna()
        if mask_nan.any():
            s = s.mask(mask_nan, None)
            
        return s
    
    # Versión escalar (Legacy support)
    if pd.isna(texto):
        return None
    
    texto = str(texto).upper()
    replacements = (
        ("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
        ("Ü", "U")
    )
    for a, b in replacements:
        texto = texto.replace(a, b)
        
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def reparar_nombres_mal_formados(df):
    """
    Replica la lógica de 'funcion_dividir_nombre_completo' de R.
    Si hay 'nombres' pero faltan apellidos (o ambos), intenta dividir 'nombres'.
    """
    # Trabajamos sobre una copia para no afectar el original externo si fuera necesario
    df = df.copy()
    
    # Aseguramos columnas existen
    for col in ['nombres', 'primer_apellido', 'segundo_apellido']:
        if col not in df.columns:
            df[col] = np.nan

    def dividir_nombre(row):
        nombres = str(row[col_b_nombres]) if pd.notna(row[col_b_nombres]) else ""
        ape1 = str(row[col_b_primer_apellido]) if pd.notna(row[col_b_primer_apellido]) else ""
        ape2 = str(row[col_b_segundo_apellido]) if pd.notna(row[col_b_segundo_apellido]) else ""
        
        # Condición de R: !is.na(nombres) & (is.na(primer_apellido) | is.na(segundo_apellido))
        # Aquí convertimos nan a "" para simplificar, la lógica de "falta apellido" es len leq 0
        necesita_correccion = (len(nombres) > 0) and (len(ape1) == 0 or len(ape2) == 0)
        
        if not necesita_correccion:
            return row[col_b_nombres], row[col_b_primer_apellido], row[col_b_segundo_apellido]
            
        # Lógica de división R:
        # 1. Limpieza de preposiciones
        nombre_limpio = re.sub(r'\s+', ' ', nombres).strip()
        regex_preposiciones = r'\b(de\s+la|de\s+las|de\s+los|de|del|la|las|los|y)\s+'
        
        # Reemplazar espacios de preposiciones por "_" temporalmente
        # En Python re.sub con función lambda para procesar el match
        def repl(m):
            return m.group(0).replace(" ", "_")
        
        nombre_pre = re.sub(regex_preposiciones, repl, nombre_limpio, flags=re.IGNORECASE)
        
        partes = [p for p in nombre_pre.split(" ") if p]
        n = len(partes)
        
        new_nombres = nombres
        new_ape1 = row[col_b_primer_apellido]
        new_ape2 = row[col_b_segundo_apellido]
        
        if n >= 3:
            # R: nombres = partes[1:(n-2)], ape1 = n-1, ape2 = n
            new_nombres = " ".join(partes[:n-2])
            new_ape1 = partes[n-2]
            new_ape2 = partes[n-1]
        elif n == 2:
            # R: nombres = partes[1], ape1 = partes[2]
            new_nombres = partes[0]
            new_ape1 = partes[1]
            new_ape2 = None # NA_character_
        else:
            # N=1 o raro
            new_nombres = nombres # Se queda como está
            new_ape1 = None
            new_ape2 = None
            
        # Limpieza final: quitar guiones bajos
        def clean_final(val):
            return val.replace("_", " ") if val else None

        return clean_final(new_nombres), clean_final(new_ape1), clean_final(new_ape2)

    # Aplicamos fila por fila (lento pero seguro para replicar lógica compleja)
    # Solo aplicamos a quienes lo necesitan para optimizar algo
    mask_necesita = (df[col_b_nombres].notna()) & (df[col_b_primer_apellido].isna() | df[col_b_segundo_apellido].isna())
    
    if mask_necesita.sum() > 0:
        print(f"  > aplicando corrección de nombres a {mask_necesita.sum()} registros...")
        # Aplicamos wrapper
        res = df[mask_necesita].apply(dividir_nombre, axis=1, result_type='expand')
        df.loc[mask_necesita, ['nombres', 'primer_apellido', 'segundo_apellido']] = res.values
        
    return df

    # --- Deduplicación (Replica exacta de R) ---
        
    # mask_curp_valida = df['es_curp_valida'] == True
    # # CORRECCIÓN: Usar CURP limpia para deduplicación (consistente con R logic si filtran por limpia)
    # # R distinct(curp) probablemente se refiere a la columna limpia si la renombraron antes,
    # # o usan la original pero filtradas por validez de limpia.
    # # Para mayor robustez, deduplicamos en base a la CURP normalizada.
    
    # df_curp_valida = df[mask_curp_valida].drop_duplicates(subset=['curp_limpia'], keep='first')
    # df_curp_invalida = df[~mask_curp_valida]
    
    # df = pd.concat([df_curp_valida, df_curp_invalida], ignore_index=True)
    
    # # 2. Deduplicar por Nombre + Fecha Inicio
    # # R: 1.8. Eliminar nombres repetidos
    # # subeR... |> mutate(nombre_concat = paste0(nombre_completo_victima, fha_de_ini))
    # # ... filter(indicadora_nombre_valido == "valido") |> distinct(nombre_concat, .keep_all = T)
    
    # mask_nombre_valido = df['es_nombre_valido'] == True
    
    # col_fecha_ini = 'fecha_inicio' if 'fecha_inicio' in df.columns else col_b_fecha_hechos
    
    # # Asegurar que fecha_inicio sea string para concatenar (R usa formato default)
    # # R paste0 usa representación string por defecto. Si es Date, es "YYYY-MM-DD". Si es NA es "NA".
    # # Pandas NaT float -> nan.
    
    # def format_date_r_style(x):
    #     if pd.isna(x):
    #         return "NA"
    #     try:
    #         return x.strftime('%Y-%m-%d')
    #     except:
    #         return str(x)

    # df['temp_fecha_str'] = df[col_fecha_ini].apply(format_date_r_style)

    # # Llave exacta: NOMBRE + FECHA_INI (sin espacio intermedio, paste0)
    # df['temp_key_dedup'] = df['nombre_completo'].fillna('NA') + df['temp_fecha_str']
    
    # df_nombre_valido = df[mask_nombre_valido].drop_duplicates(subset=['temp_key_dedup'], keep='first')
    # df_nombre_invalido = df[~mask_nombre_valido]
    
    # df = pd.concat([df_nombre_valido, df_nombre_invalido], ignore_index=True)
    # df = df.drop(columns=['temp_key_dedup', 'temp_fecha_str'])
    
    # print(f"  > Registros después de deduplicación: {len(df)}")

def preparar_rnpdno(df_rnpdno, fecha_inicio=None, fecha_fin=None):
    """
    Prepara RNPDNO enviando parámetros de fecha y dividiendo en Localizados y No Localizados.
    Nota: Las variables derivadas (nombre_completo_rnpdno, fecha_hechos_modificada, estado) 
    ya vienen calculadas desde la base maestra exportada en el ETL (Paso 1).
    """
    print("--- [2/2] Preparando RNPDNO ---")
    df = df_rnpdno.copy()
    
    # Estandarizar columnas (defensivo)
    df = standardize_columns(df, config.RNPDNO_COLUMN_MAPPING, strict=False, verbose=False)

    # Asegurar columnas con alias si vienen con sufijo _derivada_rnpdno o _rnpdno
    for std_col, der_col in [
        ('fub', 'fub_derivada_rnpdno'),
        ('fecha_hechos_modificada', 'fecha_hechos_modificada_derivada_rnpdno'),
        ('clasificacion_des', 'clasificacion_des_derivada_rnpdno'),
        ('nombre_completo_rnpdno', 'nombre_completo_derivada_rnpdno'),
        ('estado', 'estado_derivada_rnpdno'),
        ('fechahechos', 'fecha_hechos_derivada_rnpdno'),
        ('fechanacimiento', 'fecha_nacimiento_derivada_rnpdno')
    ]:
        if std_col not in df.columns or df[std_col].isna().all():
            if der_col in df.columns:
                df[std_col] = df[der_col]
            elif f"{std_col}_rnpdno" in df.columns:
                df[std_col] = df[f"{std_col}_rnpdno"]

    # Filtro de fechas (sobre fecha_hechos_modificada)
    if 'fecha_hechos_modificada' in df.columns:
        if fecha_inicio:
            print(f"  > Filtrando fecha_hechos_modificada >= {fecha_inicio} (incluyendo registros sin fecha)")
            df = df[(df['fecha_hechos_modificada'] >= pd.to_datetime(fecha_inicio, utc=True)) | (df['fecha_hechos_modificada'].isna())]
        if fecha_fin:
            print(f"  > Filtrando fecha_hechos_modificada < {fecha_fin}")
            df = df[(df['fecha_hechos_modificada'] < pd.to_datetime(fecha_fin, utc=True)) | (df['fecha_hechos_modificada'].isna())]
    else:
        print("  > ⚠️ Advertencia: No se encontró 'fecha_hechos_modificada'. Asegúrate de haber corrido el ETL completo.")
        
    # Split
    col_clasif = 'clasificacion_des' if 'clasificacion_des' in df.columns else 'clasificacion_des_derivada_rnpdno'
    no_loc = df[df[col_clasif] != 'Localizados'].copy()
    loc = df[df[col_clasif] == 'Localizados'].copy()
    
    return no_loc, loc

def _realinear_a_banci(banci_proc, df_banci):
    """Devuelve el resultado del motor indexado por la FILA DE BANCI que lo produjo.

    Sin esto, `banci_proc` trae un índice renumerado por los `concat` internos y
    asignar sus columnas a un marco indexado como BANCI alinea por etiqueta: la
    fila 0 de BANCI se queda con lo que cayó en la posición 0 de un marco
    reordenado y más corto. El efecto era silencioso —los pares eran correctos,
    pero colgaban de la carpeta equivocada— y sólo se ve comparando la CURP de la
    fila contra la del FUB que se le asignó.

    Una fila de BANCI puede aparecer dos veces (por ejemplo en `con_match` y entre
    los `skip_match`); se conserva la que trae match.
    """
    from src.matching_r import COL_IDX_ORIGEN

    if COL_IDX_ORIGEN not in banci_proc.columns:
        print(f"  ⚠️ El motor estándar no devolvió {COL_IDX_ORIGEN!r}: el resultado se "
              "alineará por posición y los matches pueden quedar en la fila equivocada.")
        return banci_proc

    proc = banci_proc.dropna(subset=[COL_IDX_ORIGEN]).copy()
    if "fub_rnpdno" in proc.columns:
        proc = proc.sort_values("fub_rnpdno", key=lambda s: s.isna(), kind="stable")

    # Los `concat` meten NaN y vuelven la columna float; un índice float NUNCA casa
    # con el RangeIndex entero de BANCI y el reindex devolvería todo vacío, que es
    # la misma falla silenciosa en otra forma.
    try:
        proc[COL_IDX_ORIGEN] = proc[COL_IDX_ORIGEN].astype(df_banci.index.dtype)
    except (TypeError, ValueError):
        pass
    proc = proc.set_index(COL_IDX_ORIGEN)
    proc.index.name = df_banci.index.name
    proc = proc[~proc.index.duplicated(keep="first")]
    return proc.reindex(df_banci.index)


def ejecutar_confronta(df_banci, df_rnpdno, fecha_inicio_banci=None, fecha_fin_banci=None,
                      fecha_inicio_rnpdno=None, fecha_fin_rnpdno=None,
                      filtrar_banci_no_localizados=True):
    """
    Ejecuta la confronta jerárquica BANCI vs RNPDNO siguiendo la lógica idéntica
    del script R 'funcion_tratamiento_banci_rnpdno_con_columnas_matcheo_ari.R'.
    
    Retorna un DataFrame consolidado con todos los registros de BANCI procesados,
    conteniendo 'id_match_rnpdno', 'tipo_match' y todas las columnas de trazabilidad.
    """
    from src.matching_r import ejecutar_confronta_r
    
    con_match, sin_match = ejecutar_confronta_r(
        df_banci=df_banci,
        df_rnpdno=df_rnpdno,
        fecha_inicio_banci=fecha_inicio_banci,
        fecha_fin_banci=fecha_fin_banci,
        fecha_inicio_rnpdno=fecha_inicio_rnpdno,
        fecha_fin_rnpdno=fecha_fin_rnpdno,
        filtrar_banci_no_localizados=filtrar_banci_no_localizados,
    )
    
    banci_proc = pd.concat([con_match, sin_match], ignore_index=True)
    banci_proc = _realinear_a_banci(banci_proc, df_banci)
    if 'fub_rnpdno' in banci_proc.columns:
        banci_proc['id_match_rnpdno'] = banci_proc['fub_rnpdno']
    else:
        banci_proc['id_match_rnpdno'] = None
        
    banci_proc['tipo_match'] = banci_proc['tipo_match'].fillna('sin_match')
    return banci_proc
