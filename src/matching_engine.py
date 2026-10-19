import pandas as pd
import numpy as np
import re
from typing import List, Optional, Union
from pathlib import Path

from src.matching import ejecutar_confronta
from src.motor_refinado import (
    motor_match_refinado,           # noqa: F401  (re-exportado desde aquí)
    leer_revisiones_sesnsp,
    descuentos_sesnsp,
    _hash_norm as _refinado_hash_norm,
)


# =====================================================================
# 1. MOTORES DE MATCH INDEPENDIENTES
# =====================================================================
#
# Todos los motores comparten la misma firma:
#   def motor_match_<nombre>(df_banci, df_rnpdno, **kwargs) -> pd.DataFrame
#
# El DataFrame devuelto tiene el MISMO ÍNDICE que df_banci y contiene
# exactamente dos columnas canónicas (más las de trazabilidad opcionales):
#   - id_match_<nombre>   : fub / identificador del RNPDNO emparejado (o None)
#   - tipo_match_<nombre> : etiqueta del subcriterio de éxito (o 'sin_match')
#
# Los motores son FUNCIONES PURAS SIN ESTADO: no modifican los DataFrames
# de entrada ni saben qué otros motores existen en el sistema.

def motor_match_estandar(df_banci: pd.DataFrame, df_rnpdno: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Motor Estándar (Jerárquico: FUB -> CURP -> Nombre).
    Sigue la lógica exacta del script R 'funcion_tratamiento_banci_rnpdno_con_columnas_matcheo_ari.R'.
    
    Devuelve DataFrame con índice idéntico a df_banci y columnas:
      - id_match_estandar
      - tipo_match_estandar
      - (y columnas de trazabilidad si están presentes)
    """
    print("  🔹 [Motor Estándar] Ejecutando FUB -> CURP -> Nombre (Lógica R)...")

    # OJO: `fecha_inicio_banci` / `fecha_fin_banci` llegan en kwargs y NO se
    # reenvían. Es un cabo suelto anterior a este cambio —`periodo_match` del perfil
    # nunca llega al motor—, no un olvido de aquí: reenviarlas ahora ACOTARÍA por
    # fecha un universo que hoy no lo está y movería los conteos del reporte diario.
    # Se deja como está y se documenta; corregirlo es una decisión aparte.
    banci_proc = ejecutar_confronta(
        df_banci, df_rnpdno,
        filtrar_banci_no_localizados=kwargs.get("filtrar_banci_no_localizados", True),
    )
    
    out = pd.DataFrame(index=df_banci.index)
    out['id_match_estandar'] = banci_proc['id_match_rnpdno'] if 'id_match_rnpdno' in banci_proc.columns else None
    out['tipo_match_estandar'] = banci_proc['tipo_match'] if 'tipo_match' in banci_proc.columns else 'sin_match'
    out['tipo_match_estandar'] = out['tipo_match_estandar'].fillna('sin_match')
    
    # Copiar columnas adicionales de trazabilidad R al DataFrame de salida.
    # `match_definitivo` sólo la tiene este motor: separa lo que va a la revisión de
    # fecha de hechos del Secretariado (ver revision_sesnsp.py).
    cols_trazabilidad = [
        'variables_match', 'verif_nombre', 'verif_curp', 'verif_fecha_nac',
        'verif_entidad', 'verif_sexo', 'tolerancia_fecha_desaparicion',
        'diferencia_dias_desaparicion', 'fecha_hechos_status', 'evaluacion_match', 'score',
        'match_definitivo',
    ]
    for col in cols_trazabilidad:
        if col in banci_proc.columns:
            out[f"{col}_estandar"] = banci_proc[col]
            
    return out


def motor_match_manual(
    df_banci:  pd.DataFrame,
    df_rnpdno: pd.DataFrame,
    ruta_verif_fecha_hechos: Optional[Union[str, Path]] = None,
    ruta_revision_manual:    Optional[Union[str, Path]] = None,
    hoja_verif:    int = 0,
    hoja_revision: int = 1,
    skiprows_verif:    int = 0,
    skiprows_revision: int = 0,
    col_mapping_verif:    Optional[dict] = None,
    col_mapping_revision: Optional[dict] = None,
    df_manual: Optional[pd.DataFrame] = None,
    usar_fub_preasignado: bool = False,
    **kwargs,
) -> pd.DataFrame:
    """
    Motor Manual / Dictámenes.

    Combina fuentes de matches ya validados manualmente:

    1. FUB pre-asignado en BANCI  ← DESACTIVADA por defecto
       La columna fub_derivada_banci / folio_rnpdno trae un FUB asignado río arriba.
       Aceptarlo marca el registro como 'match_fub_banci' sin comparar ni un solo
       atributo de identidad, así que la fuente está apagada: se activa con
       `usar_fub_preasignado=True` (perfil: `manual_usar_fub_preasignado = true`).

    2. Revisiones confirmadas del SESNSP (VALIDO/VALIDA = "SI")
       Si se proporcionan las rutas a los archivos de revisión del SESNSP
       (matches_verif_fecha_hechos_SESNSP.xlsx y revision_manual_score_SESNSP.xlsx),
       los pares confirmados (SI) se cargan y se aplican como matches.

    Parámetros:
        ruta_verif_fecha_hechos : Path al Excel de revisiones de fecha de hechos
        ruta_revision_manual    : Path al Excel de revisiones manuales por score
        hoja_verif    : hoja del primer archivo (default 0)
        hoja_revision : hoja del segundo archivo (default 1)
        df_manual     : DataFrame alternativo con columnas [id_registro_banci, fub_rnpdno]
                        para casos donde los matches provienen de una fuente personalizada

    Insumos (colocar en config.REFINADO_REVISIONES_DIR):
        - matches_verif_fecha_hechos_SESNSP.xlsx
        - revision_manual_score_SESNSP.xlsx
    """
    print("  🔹 [Motor Manual] Ejecutando matches pre-validados...")

    out = pd.DataFrame(index=df_banci.index)
    out['id_match_manual']    = None
    out['tipo_match_manual']  = 'sin_match'
    out['score_manual']       = 0
    out['variables_match_manual'] = ''
    # Todos los FUB validados de esa fila, separados por coma. La cascada consolida
    # uno solo por registro; esta columna conserva los demás para que el lado RNPDNO
    # no pierda personas cuya pareja fue confirmada a mano.
    out['fubs_confirmados_manual'] = None

    # ── Fuente 1: FUB ya asignado en BANCI ───────────────────────────────────
    # DESACTIVADA por defecto (`usar_fub_preasignado=False`, perfil
    # `manual_usar_fub_preasignado`). Aceptar el `folio_RNPDNO` que BANCI ya trae
    # convierte en match un identificador pre-asignado río arriba SIN comparar
    # nombre, CURP, fecha de nacimiento, fecha de hechos ni carpeta: la única
    # verificación es que el FUB exista en el universo RNPDNO. Eso no es evidencia,
    # y además tapaba matches mejor sustentados (se quedaba con registros que el
    # SESNSP ya había confirmado a mano y con otros que el refinado podía resolver).
    #
    # Con la fuente apagada esos registros quedan libres: el FUB sigue siendo una
    # señal del motor refinado —genera candidatos por `idx_fub_b` y sostiene un
    # definitivo como "misma persona en otra carpeta (FUB identico)"—, pero ahí
    # tiene que pasar por los guardianes anti-homónimo.
    #
    # Solo se crea match si el FUB existe en df_rnpdno (el universo que el motor
    # refinado va a usar). Esto alinea con v6 donde los FUB matches solo se
    # producen cuando el RNPDNO target está realmente en el universo de búsqueda.
    _CANDS_FUB_BANCI = ['fub_derivada_banci', 'fub_banci', 'folio_rnpdno', 'fub_ok', 'fub']
    col_fub_banci = next(
        (c for c in _CANDS_FUB_BANCI if c in df_banci.columns), None
    ) if usar_fub_preasignado else None
    if not usar_fub_preasignado:
        print("    FUB pre-asignado en BANCI: DESACTIVADO "
              "(perfil: manual_usar_fub_preasignado = false)")
    if col_fub_banci:
        mask_fub = (
            df_banci[col_fub_banci].notna()
            & (df_banci[col_fub_banci].astype(str).str.strip() != '')
            & (~df_banci[col_fub_banci].astype(str).isin(['nan', 'None', 'NA', '<NA>']))
        )
        # Validar que el FUB exista en df_rnpdno (el universo real de búsqueda)
        _CANDS_FUB_RN = ['fub_derivada_rnpdno', 'fub_rnpdno', 'fub', 'id_persona_rnpdno']
        col_fub_rn = next((c for c in _CANDS_FUB_RN if c in df_rnpdno.columns), None)
        if col_fub_rn:
            _valid_fubs = set(
                df_rnpdno[col_fub_rn].dropna().astype(str).str.strip().str.upper()
            )
            mask_fub = mask_fub & (
                df_banci[col_fub_banci].astype(str).str.strip().str.upper().isin(_valid_fubs)
            )
        if mask_fub.sum() > 0:
            out.loc[mask_fub, 'id_match_manual']   = (
                df_banci.loc[mask_fub, col_fub_banci].astype(str).str.strip()
            )
            out.loc[mask_fub, 'tipo_match_manual'] = 'match_fub_banci'
            out.loc[mask_fub, 'score_manual']      = 100
            out.loc[mask_fub, 'variables_match_manual'] = f'FUB pre-asignado en BANCI ({col_fub_banci})'
            print(f"    FUB pre-asignado en BANCI (validado en RNPDNO): {mask_fub.sum():,} registros")

    # ── Fuente 2: DataFrame de matches manuales explícito ────────────────────
    if df_manual is not None and not df_manual.empty:
        def _busca(df, cands):
            def _k(x): return re.sub(r'[\s._-]+', '', str(x)).upper()
            mapa = {_k(c): c for c in df.columns}
            return next((mapa[_k(c)] for c in cands if _k(c) in mapa), '')

        col_rb = _busca(df_manual, ['id_registro_banci', 'id_registro', 'id_banci'])
        col_rf = _busca(df_manual, ['fub_rnpdno', 'fub', 'id_rnpdno'])
        col_rb_banci = next(
            (c for c in ['id_registro_banci', 'id_registro', 'id_persona_banci', 'id_persona']
             if c in df_banci.columns), None
        )
        if col_rb and col_rf and col_rb_banci:
            # Construir mapa {id_registro_banci -> fub_rnpdno}
            mapa_manual = (
                df_manual[[col_rb, col_rf]]
                .dropna()
                .set_index(col_rb)[col_rf]
                .map(_refinado_hash_norm)
                .to_dict()
            )
            ids_banci = df_banci[col_rb_banci].map(_refinado_hash_norm)
            mask_manual = ids_banci.isin(mapa_manual)
            if mask_manual.sum() > 0:
                out.loc[mask_manual, 'id_match_manual'] = (
                    ids_banci[mask_manual].map(mapa_manual)
                )
                out.loc[mask_manual, 'tipo_match_manual']       = 'match_manual_dictamen'
                out.loc[mask_manual, 'score_manual']            = 100
                out.loc[mask_manual, 'variables_match_manual']  = 'match del DataFrame manual explícito'
                print(f"    Dictamen manual (df_manual): {mask_manual.sum():,} registros")

    # ── Fuente 3: Revisiones confirmadas del SESNSP ───────────────────────────
    # Sólo el veredicto 'SI' crea match. Un 'NO' en matches_verif_fecha_hechos
    # significa que el par fue revisado y RECHAZADO (fecha de hechos muy distinta):
    # cierra el caso —el registro sale del universo del motor refinado— pero NO se
    # asigna como match. Es el mismo criterio de normalizar_folios_v6.py.
    #
    # El pegado NO se hace por `id_registro`: ese identificador es un sha1 que
    # construye el SESNSP, no viene en el BANCI de origen y no se puede reproducir,
    # así que el cruce daba cero y las 665 confirmaciones nunca se aplicaban.
    # `descuentos_sesnsp` vuelve a ligar cada revisión con su registro de BANCI por
    # contenido (entidad + carpeta + curp / nombre / fecha de nacimiento).
    if ruta_verif_fecha_hechos or ruta_revision_manual:
        _rev = leer_revisiones_sesnsp(
            ruta_verif_fecha_hechos, ruta_revision_manual,
            hoja_verif, hoja_revision,
            skiprows_verif, skiprows_revision,
            col_mapping_verif, col_mapping_revision,
        )
        _, _, _, confirmados = descuentos_sesnsp(df_banci, _rev)

        # Un FUB sólo se acepta si existe en el universo RNPDNO que se está usando;
        # si apunta a un localizado o a un caso pre-sexenio, se descarta ESE FUB (no el
        # registro) para que el motor refinado pueda buscar su match real.
        _CANDS_FUB_RN2 = ['fub_derivada_rnpdno', 'fub_rnpdno', 'fub', 'id_persona_rnpdno']
        _col_fub_rn2 = next((c for c in _CANDS_FUB_RN2 if c in df_rnpdno.columns), None)
        if _col_fub_rn2:
            _fubs_validos = set(
                df_rnpdno[_col_fub_rn2].dropna().astype(str).str.strip().str.upper()
            )
            confirmados = {i: [f for f in fs if f in _fubs_validos]
                           for i, fs in confirmados.items()}
            confirmados = {i: fs for i, fs in confirmados.items() if fs}

        if confirmados:
            idx = pd.Index([i for i in confirmados if i in out.index])
            libres = (out.loc[idx, 'tipo_match_manual'] == 'sin_match').to_numpy()
            idx = idx[libres]
            if len(idx):
                # La fila lleva UN id (el primero, de la fuente de mayor peso) porque
                # la cascada consolida un match por registro de BANCI. Los demás FUB
                # validados viajan en `fubs_confirmados_manual`: se reclaman del lado
                # del RNPDNO, donde cada FUB es una persona distinta con match en BANCI.
                out.loc[idx, 'id_match_manual']       = [confirmados[i][0] for i in idx]
                out.loc[idx, 'tipo_match_manual']     = 'match_confirmado_sesnsp'
                out.loc[idx, 'score_manual']          = 100
                out.loc[idx, 'variables_match_manual'] = 'revisión confirmada SESNSP'
                out.loc[idx, 'fubs_confirmados_manual'] = [
                    ",".join(confirmados[i]) for i in idx
                ]
                n_extra = sum(len(confirmados[i]) - 1 for i in idx)
                print(f"    Confirmados SESNSP: {len(idx):,} registros"
                      + (f" ({n_extra:,} FUB adicionales del mismo registro)" if n_extra else ""))

    n = (out['tipo_match_manual'] != 'sin_match').sum()
    print(f"  ✅ [Motor Manual] {n:,} / {len(df_banci):,} registros con match manual")
    return out


# =====================================================================
# 2. ORQUESTADOR DE EJECUCIÓN MULTI-MOTOR
# =====================================================================

# =====================================================================
# 3. COMBINADOR FLEXIBLE EN CASCADA / PRIORIDAD
# =====================================================================

def combinar_matches_cascada(
    df_con_matches: pd.DataFrame, 
    orden_prioridad: List[str], 
    sufijo_salida: str = "consolidado"
) -> pd.DataFrame:
    """
    Combina los resultados de los motores registrados siguiendo un orden de prioridad (Cascada).
    
    Parámetros:
        df_con_matches: DataFrame de BANCI enriquecido con los resultados de los motores.
        orden_prioridad: Lista de motores en orden de preferencia (ej. ['estandar']).
        sufijo_salida: Etiqueta para nombrar las columnas resultantes.
        
    Genera las columnas:
      - id_match_<sufijo_salida>
      - tipo_match_<sufijo_salida>
      - metodo_origen_<sufijo_salida>
      
    Asigna los aliases compatibles 'id_match_rnpdno' y 'tipo_match'
    para que todo el pipeline posterior funcione sin cambios.
    """
    df_res = df_con_matches.copy()
    
    col_id_res = f"id_match_{sufijo_salida}"
    col_tipo_res = f"tipo_match_{sufijo_salida}"
    col_origen_res = f"metodo_origen_{sufijo_salida}"
    
    df_res[col_id_res] = None
    df_res[col_tipo_res] = 'sin_match'
    df_res[col_origen_res] = None
    
    print(f"\n🔀 Combinando matches en cascada (Prioridad: {' -> '.join(orden_prioridad)})...")
    
    for motor in orden_prioridad:
        col_id_motor = f"id_match_{motor}"
        col_tipo_motor = f"tipo_match_{motor}"
        
        if col_id_motor not in df_res.columns:
            print(f"  ⚠️ Advertencia: El motor '{motor}' no fue ejecutado previa a la combinación. Se omite.")
            continue
            
        mask_pendiente = df_res[col_id_res].isna()
        mask_motor_tiene_match = df_res[col_id_motor].notna() & (df_res[col_tipo_motor] != 'sin_match')
        
        mask_aplicar = mask_pendiente & mask_motor_tiene_match
        
        df_res.loc[mask_aplicar, col_id_res] = df_res.loc[mask_aplicar, col_id_motor]
        df_res.loc[mask_aplicar, col_tipo_res] = motor
        df_res.loc[mask_aplicar, col_origen_res] = motor
        
        col_subcriterio = f"subcriterio_match_{sufijo_salida}"
        if col_subcriterio not in df_res.columns:
            df_res[col_subcriterio] = 'sin_match'
        df_res.loc[mask_aplicar, col_subcriterio] = df_res.loc[mask_aplicar, col_tipo_motor]
        
        # Copiar también las columnas de trazabilidad asociadas a ese motor
        cols_trazabilidad = [
            'variables_match', 'verif_nombre', 'verif_curp', 'verif_fecha_nac',
            'verif_entidad', 'verif_sexo', 'tolerancia_fecha_desaparicion',
            'diferencia_dias_desaparicion', 'fecha_hechos_status', 'evaluacion_match', 'score'
        ]
        for col_t in cols_trazabilidad:
            col_t_motor = f"{col_t}_{motor}"
            if col_t_motor in df_res.columns:
                if col_t not in df_res.columns:
                    df_res[col_t] = None
                df_res.loc[mask_aplicar, col_t] = df_res.loc[mask_aplicar, col_t_motor]
        
        n_agregados = mask_aplicar.sum()
        print(f"  > Motor '{motor}' aportó {n_agregados:,} nuevos registros matcheados.")

    # ── Etiqueta COMBINADA: los motores que SOSTIENEN el match asignado ──────
    # La cascada elige UN ganador (el de mayor prioridad) y su FUB es el que queda
    # como `id_match_rnpdno`. Que otro motor también haya matcheado la fila NO
    # significa que corrobore: puede haber apuntado a OTRA persona. Sólo se acredita
    # a un motor cuando su `id_match_<motor>` coincide con el FUB asignado; si apunta
    # a otro, es un DESACUERDO y se cuenta aparte. Confundir las dos cosas inflaría
    # la corroboración justo donde los métodos se contradicen.
    col_motores_res = f"motores_match_{sufijo_salida}"
    id_ganador = _norm_id(df_res[col_id_res])
    motores_por_fila = [[] for _ in range(len(df_res))]
    desacuerdos = {}
    for motor in orden_prioridad:
        col_id_motor, col_tipo_motor = f"id_match_{motor}", f"tipo_match_{motor}"
        if col_id_motor not in df_res.columns:
            continue
        tiene = (df_res[col_id_motor].notna()
                 & (df_res[col_tipo_motor] != 'sin_match')
                 & (df_res[col_tipo_res] != 'sin_match'))
        mismo = tiene & (_norm_id(df_res[col_id_motor]) == id_ganador)
        for i in np.flatnonzero(mismo.to_numpy()):
            motores_por_fila[i].append(motor)
        n_dis = int((tiene & ~mismo).sum())
        if n_dis:
            desacuerdos[motor] = n_dis
    df_res[col_motores_res] = [", ".join(m) if m else 'sin_match'
                               for m in motores_por_fila]

    n_totales = (df_res[col_tipo_res] != 'sin_match').sum()
    print(f"🏁 Resultado Match ('{sufijo_salida}'): {n_totales:,} / {len(df_res):,} registros matcheados.")
    combos = df_res.loc[df_res[col_tipo_res] != 'sin_match', col_motores_res].value_counts()
    print("   Métodos que sostienen el FUB asignado:")
    for combo, n in combos.items():
        print(f"     {combo:<34} {n:>7,}")
    if desacuerdos:
        print("   Desacuerdos (el motor matcheó la fila pero señalando a OTRO FUB):")
        for motor, n in desacuerdos.items():
            print(f"     {motor:<34} {n:>7,}")

    # Aliases backward-compatible.
    #   tipo_match    → TODOS los métodos que hicieron match, separados por coma
    #   metodo_origen → sólo el ganador de la cascada (el que aporta id y subcriterio)
    df_res['id_match_rnpdno'] = df_res[col_id_res]
    df_res['tipo_match'] = df_res[col_motores_res]
    df_res['metodo_origen'] = df_res[col_origen_res]
    df_res['subcriterio_match'] = df_res[col_subcriterio]

    return df_res


def _norm_id(s: pd.Series) -> pd.Series:
    """FUB comparable entre motores: sin espacios y en mayúsculas. Los nulos quedan
    como cadena vacía, que nunca iguala a un FUB real."""
    return s.astype(str).str.strip().str.upper().where(s.notna(), "")


def auditar_comparacion_motores(df_con_matches: pd.DataFrame, motores: List[str]) -> pd.DataFrame:
    """
    Genera una matriz comparativa del comportamiento de cada motor de match.
    """
    registros = []
    total = len(df_con_matches)
    
    for m in motores:
        col_id = f"id_match_{m}"
        col_tipo = f"tipo_match_{m}"
        if col_id in df_con_matches.columns:
            cnt = (df_con_matches[col_tipo] != 'sin_match').sum()
            pct = round((cnt * 100) / total, 2) if total > 0 else 0
            registros.append({"Motor": m, "Total Matches": cnt, "Porcentaje %": pct})
            
    return pd.DataFrame(registros)
