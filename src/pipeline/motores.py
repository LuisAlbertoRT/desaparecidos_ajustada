"""CAPA A · Ejecución de los motores de match y consolidación en cascada.

Esta es la etapa cara del pipeline (minutos). Su resultado se cachea con
`Settings.clave_matching`, que NO depende del período, el estatus, el subfiltro
ni la entidad. Cambiar cualquiera de esos cuatro no vuelve a ejecutar nada de
aquí.

Antes esta lógica vivía en las celdas 9–12 de 4_Generacion_Indicadores.ipynb.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.matching_engine import (
    motor_match_estandar,
    motor_match_manual,
    motor_match_refinado,
    combinar_matches_cascada,
    auditar_comparacion_motores,
)
from src.pipeline.carga import Fuentes
from src.pipeline.derivadas import columna_fecha_periodo
from src.pipeline.reglas import aplicar_reglas_motores
from src.settings import Settings

# Versión de lo que devuelve esta capa. SÚBELA al cambiar las columnas que salen
# o sus nombres: entra en `clave_matching`, que viaja en `version_match` de las
# bases exportadas. El caché no depende de que se suba: su llave ya incluye el
# código de la capa (`huella.huella_codigo`).
VERSION_MATCHING = 3

# Los motores trabajan con los nombres de columna del script de R y de
# normalizar_folios_v6 (`fub`, `fechahechos`, `llave`…). `_correr_motor` les
# entrega una copia con estos nombres; lo que devuelven son sólo sus columnas de
# resultado, así que ningún nombre interno llega a un archivo.
_NOMBRES_MOTORES_RN = {
    "fub_rnpdno": "fub",
    "estatus_rnpdno": "estatus",
    "nombre_vic_rnpdno": "nombre_vic",
    "primerapellido_vic_rnpdno": "primerapellido_vic",
    "segundoapellido_vic_rnpdno": "segundoapellido_vic",
    "sexo_rnpdno": "sexo",
    "delitolocalizacion_rnpdno": "delitolocalizacion",
    "dependencia_origen_rnpdno": "dependencia_origen",
    "expedientes_rnpdno": "expediente",
    "fechanacimiento_derivada_rnpdno": "fechanacimiento",
    "fechahechos_derivada_rnpdno": "fechahechos",
    "fechapercato_derivada_rnpdno": "fechapercato",
    "fechacaptura_derivada_rnpdno": "fechacaptura",
    "fechalocaliza_derivada_rnpdno": "fechalocaliza",
    "fecha_consulta_derivada_rnpdno": "fecha_consulta",
    "idestado_derivada_rnpdno": "idestado",
    "idmunicipio_derivada_rnpdno": "idmunicipio",
    "clasificacion_des_derivada_rnpdno": "clasificacion_des",
    "fecha_hechos_modificada_derivada_rnpdno": "fecha_hechos_modificada",
}
_NOMBRES_MOTORES_BA = {
    "llave_banci": "llave",
    "ntra_ci_banci": "ntra_ci",
    "fha_de_ini_banci": "fha_de_ini",
    "id_mun_hchos_banci": "id_mun_hchos",
    "delito_hom_banci": "delito_hom",
    "sexo_banci": "sexo",
    "folio_rnpdno_banci": "folio_rnpdno",
    "fue_delito_banci": "fue_delito",
    "fub_ok_banci": "fub_ok",
    "entidad_derivada_banci": "entidad",
    "fha_de_hchos_derivada_banci": "fha_de_hchos",
    "fha_nac_derivada_banci": "fha_nac",
    "localizado_o_no_localizado_derivada_banci": "localizado_o_no_localizado",
    "nombres_derivada_banci": "nombres",
    "primer_apellido_derivada_banci": "primer_apellido",
    "segundo_apellido_derivada_banci": "segundo_apellido",
}

# ── Lo que devuelve la capa A ────────────────────────────────────────────────
# Del BANCI del ETL, sólo las columnas que leen las capas siguientes
# (`derivar_banci` y la exportación de llaves); las demás siguen en Resultado_2.
COLS_BANCI_SALIDA = [
    "entidad_derivada_banci", "id_carpeta_derivada_banci", "sexo_banci",
    "id_mun_hchos_banci", "fha_de_hchos_derivada_banci",
    "localizado_o_no_localizado_derivada_banci", "fue_delito_banci",
    "delito_hom_banci", "curp_valida_derivada_banci",
]
# El resultado del cruce, con el sufijo de las dos bases de las que sale. La
# cascada y las reglas trabajan con los nombres de la izquierda.
_NOMBRES_CRUCE = {
    "id_match_rnpdno": "fub_derivada_rnpdno_banci",
    "tipo_match": "tipo_match_derivada_rnpdno_banci",
    "metodo_origen": "metodo_origen_derivada_rnpdno_banci",
    "subcriterio_match": "subcriterio_match_derivada_rnpdno_banci",
    "score": "score_derivada_rnpdno_banci",
    "variables_match": "variables_match_derivada_rnpdno_banci",
    "fubs_confirmados_manual": "fubs_confirmados_manual_derivada_rnpdno_banci",
}


@dataclass
class ResultadoMatching:
    """Salida de la capa A."""
    banci: pd.DataFrame            # BANCI (COLS_BANCI_SALIDA) + el cruce, `*_derivada_rnpdno_banci`
    fubs_matcheados: set[str]      # FUBs del RNPDNO reclamados por algún motor
    mapa_tipo_match: dict          # FUB → métodos que lo resolvieron ("estandar, manual")
    auditoria: pd.DataFrame        # matches aportados por cada motor
    verif_fecha: pd.DataFrame      # pares a revisar por fecha de hechos (ver _cola_verif_fecha)
    candidatos: pd.DataFrame       # candidatos a revisión manual del refinado (ver _cola_candidatos)


def ejecutar_matching(cfg: Settings, fuentes: Fuentes, verbose: bool = True) -> ResultadoMatching:
    rn, ba = fuentes.rn, fuentes.ba
    orden = list(cfg.orden_prioridad_cascada)
    rn_universo = _universo_rnpdno(rn, cfg, verbose=verbose)

    if cfg.cascada_en_ejecucion:
        resultados, auditoria = _correr_en_cadena(cfg, ba, rn, rn_universo, orden, verbose)
    else:
        resultados, auditoria = _correr_en_paralelo(cfg, ba, rn, rn_universo, orden, verbose)

    banci = combinar_matches_cascada(
        resultados, orden_prioridad=orden, sufijo_salida="consolidado"
    )

    # ── CONSOLIDADO ─────────────────────────────────────────────────────────
    # Un mismo FUB puede ser alcanzado por motores distintos a través de FILAS
    # distintas de BANCI (la misma persona aparece en varias carpetas). Se listan
    # todos los métodos, en el orden de la cascada, en vez de quedarse con el de la
    # primera fila: ese desempate dependía del orden del archivo de BANCI, no de una
    # regla, y podía mover la atribución entre cortes sin que nada más cambiara.
    matches = banci[banci["tipo_match"] != "sin_match"]
    matches = matches[matches["id_match_rnpdno"].notna()]
    fubs = set(matches["id_match_rnpdno"].astype(str).unique())

    por_fub: dict[str, set[str]] = {}
    for fub, etiqueta in zip(matches["id_match_rnpdno"].astype(str),
                             matches["tipo_match"].astype(str)):
        por_fub.setdefault(fub, set()).update(
            t for t in (p.strip() for p in etiqueta.split(",")) if t
        )

    # FUB adicionales de un registro con VARIAS parejas confirmadas a mano. La fila de
    # BANCI sólo puede llevar un `id_match_rnpdno`, pero del lado del RNPDNO cada FUB
    # es una PERSONA distinta cuya pareja un revisor ya validó: dejarlos fuera perdía
    # personas por una limitación del formato, no por falta de evidencia.
    n_extra = 0
    if "fubs_confirmados_manual" in banci.columns:
        vivos = banci[banci["tipo_match_manual"] != "sin_match"]
        for lista in vivos["fubs_confirmados_manual"].dropna().astype(str):
            for f in (p.strip() for p in lista.split(",")):
                if f and f not in fubs:
                    fubs.add(f)
                    n_extra += 1
                por_fub.setdefault(f, set()).add("manual")

    mapa = {f: ", ".join(m for m in orden if m in s) for f, s in por_fub.items()}
    if verbose and n_extra:
        print(f"\n  ＋ {n_extra:,} FUB adicionales reclamados por registros de BANCI con "
              f"más de una pareja confirmada a mano (relación muchos a muchos).")

    if verbose:
        pct = len(fubs) / len(banci) if len(banci) else 0
        print(f"\n🏁 {len(fubs):,} FUBs únicos matcheados ({pct:.1%})  |  "
              f"{(banci['tipo_match'] == 'sin_match').sum():,} sin match")
        combos = pd.Series(list(mapa.values())).value_counts()
        print("   Métodos que sostienen cada FUB:")
        for combo, n in combos.items():
            print(f"     {combo:<34} {n:>7,}")

    verif = _cola_verif_fecha(banci, rn_universo, verbose)
    candidatos = _cola_candidatos(banci, verbose)
    return ResultadoMatching(banci=_salida(banci), fubs_matcheados=fubs,
                             mapa_tipo_match=mapa, auditoria=auditoria,
                             verif_fecha=verif, candidatos=candidatos)


# ── Cola de revisión de fecha de hechos (para el Secretariado) ───────────────
# Pares que un motor sostiene como match pero que la fecha de hechos no confirma.
# Es lo que antes se mandaba al Secretariado para que dijera si el par vale:
#   estándar → `match_definitivo_estandar == "DIFIERE"`: la regla con que se partía
#              la base del script de R (más de 10 días de diferencia).
#   refinado → los definitivos cuya fecha no cupo en ±10 días o que no la tienen:
#              la regla de normalizar_folios_v6.py (`matches_verif_fecha_hechos_v6`).
#              Sólo los de filas que el refinado sostiene: v6 corría sobre lo que
#              el script de R dejaba sin match, que en la cascada es lo que no ganó
#              ni el manual ni el estándar.
# Sólo entran pares cuyo FUB está en el universo RNPDNO del motor manual: un SI del
# Secretariado sobre otro FUB no tendría efecto, porque el manual lo descarta. Lo que
# el Secretariado ya revisó se descuenta al exportar (`revision_sesnsp`), que es
# donde se leen sus respuestas.
_COLS_TRAZA_REVISION = [
    "evaluacion_match", "score", "variables_match", "fecha_hechos_status",
    "verif_nombre", "verif_curp", "verif_carpeta", "verif_entidad",
    "verif_sexo", "verif_fecha_nac",
]


def _cola_verif_fecha(banci: pd.DataFrame, rn_universo: pd.DataFrame,
                      verbose: bool = True) -> pd.DataFrame:
    """Un par (fila de BANCI, FUB) por renglón. Si los dos motores proponen el mismo
    par sale una vez, con `motor = "estandar, refinado"` y la trazabilidad del
    estándar, que va antes en la cascada."""
    fila = np.arange(len(banci))
    partes = []

    if "match_definitivo_estandar" in banci.columns:
        # La oferta original: si una regla la anuló, quedó en `*_anulado`.
        fub = banci["id_match_estandar"]
        if "id_match_estandar_anulado" in banci.columns:
            fub = banci["id_match_estandar_anulado"].where(
                banci["id_match_estandar_anulado"].notna(), fub)
        m = banci["match_definitivo_estandar"].eq("DIFIERE").to_numpy()
        # El script de R no compara carpetas: su `verif_carpeta` es "NO APLICA".
        traza = {c: banci.get(f"{c}_estandar", pd.Series("NO APLICA", index=banci.index))
                 for c in _COLS_TRAZA_REVISION}
        partes.append(pd.DataFrame({"fila": fila[m], "fub": fub.to_numpy()[m],
                                    "motor": "estandar",
                                    **{c: s.to_numpy()[m] for c, s in traza.items()}}))

    if "fecha_hechos_status_refinado" in banci.columns:
        m = (banci["metodo_origen"].eq("refinado")
             & ~banci["fecha_hechos_status_refinado"].fillna("").str.startswith("COINCIDE")
             ).to_numpy()
        partes.append(pd.DataFrame({"fila": fila[m],
                                    "fub": banci["id_match_refinado"].to_numpy()[m],
                                    "motor": "refinado",
                                    **{c: banci[f"{c}_refinado"].to_numpy()[m]
                                       for c in _COLS_TRAZA_REVISION}}))

    cols = ["fila", "fub", "motor"] + _COLS_TRAZA_REVISION
    cola = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=cols)
    n_prop = cola["motor"].value_counts().to_dict()

    validos = set(rn_universo["fub_rnpdno"].dropna().astype(str).str.strip().str.upper())
    cola = cola[cola["fub"].astype(str).str.strip().str.upper().isin(validos)]
    n_univ = cola["motor"].value_counts().to_dict()

    motores_par = cola.groupby(["fila", "fub"], sort=False)["motor"].agg(", ".join)
    cola = cola.drop_duplicates(["fila", "fub"], keep="first").set_index(["fila", "fub"])
    cola["motor"] = motores_par
    cola = cola.reset_index().sort_values("fila", kind="stable")[cols]

    if verbose:
        print("\n📝 Cola de revisión de fecha de hechos (pares):")
        for mt in ("estandar", "refinado"):
            print(f"     {mt:<10} {n_prop.get(mt, 0):>6,} propuestos · "
                  f"{n_univ.get(mt, 0):>6,} con FUB en el universo")
        print(f"     {len(cola):,} pares únicos · {cola['fila'].nunique():,} filas de BANCI")
    return _nombres_cola(cola)


def _cola_candidatos(banci: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Candidatos a revisión manual: el mejor candidato que el refinado propuso para
    cada registro que quedó sin match. Es la lista de `revision_manual_v6.xlsx` de
    normalizar_folios_v6.py (allá con todos los candidatos ordenados; este motor
    conserva sólo el primero).

    `excluir_revision_manual` los retiró de la oferta, así que su FUB quedó en
    `*_anulado`; el resto de la trazabilidad sigue en las columnas del refinado. Sólo
    entran registros sin match final: uno que ya emparejó otro motor no necesita
    candidato. En un perfil en cadena no hay de esos, porque el refinado sólo ve lo que
    los demás dejaron.
    """
    cols = ["fila", "fub", "motor"] + _COLS_TRAZA_REVISION
    if "tipo_match_refinado_anulado" not in banci.columns:
        return _nombres_cola(pd.DataFrame(columns=cols))
    m = (banci["tipo_match_refinado_anulado"].eq("revision manual")
         & banci["metodo_origen"].isna()).to_numpy()
    cola = pd.DataFrame({"fila": np.arange(len(banci))[m],
                         "fub": banci["id_match_refinado_anulado"].to_numpy()[m],
                         "motor": "refinado",
                         **{c: banci[f"{c}_refinado"].to_numpy()[m]
                            for c in _COLS_TRAZA_REVISION}})[cols]
    if verbose:
        print(f"📝 Candidatos a revisión manual: {len(cola):,} registros de BANCI")
    return _nombres_cola(cola)


def _nombres_cola(cola: pd.DataFrame) -> pd.DataFrame:
    return cola.rename(columns={
        "fila": "fila_derivada_banci",
        **{c: f"{c}_derivada_rnpdno_banci" for c in cola.columns if c != "fila"},
    }).reset_index(drop=True)


def _salida(banci: pd.DataFrame) -> pd.DataFrame:
    """Deja sólo lo que leen las capas siguientes, con los nombres del cruce.

    Es el frame que reciben la capa B, la exportación de llaves y las bases del
    Secretariado. No sale el detalle de cada motor
    (`*_estandar`, `*_manual`, `*_refinado`), ni las copias `*_consolidado` de la
    cascada, ni los motivos de anulación: nadie los lee.
    """
    nombres = dict(_NOMBRES_CRUCE)
    # La oferta que anuló una regla (`reglas._anular_motor`): de ahí rescata la
    # exportación de llaves los candidatos a revisión manual.
    for c in banci.columns:
        if c.startswith(("tipo_match_", "id_match_")) and c.endswith("_anulado"):
            nombres[c] = f"{c}_derivada_rnpdno_banci"
    cruce = [c for c in nombres if c in banci.columns]
    return banci[COLS_BANCI_SALIDA + cruce].rename(columns=nombres)


# ─────────────────────────────────────────────────────────────────────────────
# Las dos formas de correr los motores
#
# PARALELO (default) · los tres ven el universo completo y opinan por separado.
# Cuesta lo que cuesta el más lento aplicado a TODO, pero es lo que permite saber
# que dos métodos independientes llegaron al mismo FUB (`motores_match_*`) y en
# cuántas filas se contradicen.
#
# EN CADENA · cada motor recibe sólo lo que el anterior no resolvió, en el orden
# de `orden_prioridad_cascada`. El refinado —que es el caro— deja de mirar las
# filas ya resueltas.
#
# El orden de ejecución de la cadena es el de PRIORIDAD y no al revés. Con el
# estándar al frente, una fila que un revisor del SESNSP confirmó a mano saldría
# del flujo antes de que el motor manual pudiera opinar: el algoritmo pisaría al
# revisor sin dejar rastro. Poner `manual` primero no cuesta nada —no busca, sólo
# transcribe pares ya validados— y preserva el mismo ganador que elegiría la
# cascada.
# ─────────────────────────────────────────────────────────────────────────────
def _correr_en_paralelo(cfg: Settings, ba: pd.DataFrame, rn: pd.DataFrame,
                        rn_universo: pd.DataFrame, orden: list[str],
                        verbose: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    resultados = ba.copy()
    for i, motor in enumerate(("estandar", "manual", "refinado"), 1):
        if verbose:
            print(f"⚡ [{i}/3] Motor {motor.upper()}... "
                  f"(BANCI: {len(ba):,}, RNPDNO: {len(rn_universo):,})")
        res = _correr_motor(motor, cfg, ba, rn, rn_universo, verbose)
        resultados = _pegar(resultados, _normalizar(res, motor, ba.index))
        if verbose:
            print(f"  ✅ {motor}: {_n_match(resultados, motor):,} / {len(ba):,}")

    auditoria = auditar_comparacion_motores(resultados, orden)
    if verbose:
        print("\n📊 Resumen comparativo de motores (antes de las reglas):")
        print(auditoria.to_string(index=False))

    resultados = aplicar_reglas_motores(resultados, rn, cfg, orden, verbose=verbose)
    return resultados, auditoria


def _correr_en_cadena(cfg: Settings, ba: pd.DataFrame, rn: pd.DataFrame,
                      rn_universo: pd.DataFrame, orden: list[str],
                      verbose: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    resultados = ba.copy()
    pendientes = ba.index
    if verbose:
        print(f"\n🔗 Motores EN CADENA ({' → '.join(orden)}): cada uno recibe sólo el "
              f"remanente del anterior.")

    for i, motor in enumerate(orden, 1):
        sub = ba.loc[pendientes]
        if verbose:
            print(f"\n⚡ [{i}/{len(orden)}] Motor {motor.upper()}... "
                  f"(BANCI pendiente: {len(sub):,}, RNPDNO: {len(rn_universo):,})")
        if sub.empty:
            resultados = _pegar(resultados, _normalizar(None, motor, ba.index))
            continue

        res = _correr_motor(motor, cfg, sub, rn, rn_universo, verbose)
        resultados = _pegar(resultados, _normalizar(res, motor, ba.index))

        # Las reglas se aplican AQUÍ, antes de decidir qué pasa al siguiente motor.
        # Un match que la regla anula no puede llevarse la fila consigo: tiene que
        # devolverla a la cadena para que el motor siguiente lo intente.
        resultados = aplicar_reglas_motores(resultados, rn, cfg, [motor], verbose=verbose)

        vivos = (resultados[f"tipo_match_{motor}"] != "sin_match") & \
                resultados[f"id_match_{motor}"].notna()
        resueltas = resultados.index[vivos]
        pendientes = pendientes[~pendientes.isin(resueltas)]
        if verbose:
            print(f"  ✅ {motor}: {int(vivos.sum()):,} resueltas  |  "
                  f"quedan {len(pendientes):,} para el siguiente motor")

    auditoria = auditar_comparacion_motores(resultados, orden)
    if verbose:
        print("\n📊 Aportación de cada motor (en cadena: cada uno vio sólo el remanente):")
        print(auditoria.to_string(index=False))
    return resultados, auditoria


def _correr_motor(motor: str, cfg: Settings, ba: pd.DataFrame, rn: pd.DataFrame,
                  rn_universo: pd.DataFrame, verbose: bool) -> pd.DataFrame:
    """Corre UN motor sobre el subconjunto de BANCI que se le entregue."""
    if motor == "refinado" and cfg.filtrar_banci_no_localizados:
        ba = _banci_no_localizados(ba, cfg)
    ba = ba.rename(columns=_NOMBRES_MOTORES_BA)
    rn = rn.rename(columns=_NOMBRES_MOTORES_RN)
    rn_universo = rn_universo.rename(columns=_NOMBRES_MOTORES_RN)
    if motor == "estandar":
        ini, fin = cfg.rango_periodo(cfg.periodo_match)
        return motor_match_estandar(
            ba, rn, fecha_inicio_banci=ini, fecha_fin_banci=fin,
            filtrar_banci_no_localizados=cfg.filtrar_banci_no_localizados,
        )
    if motor == "manual":
        return motor_match_manual(ba, rn_universo, **cfg.params_motores["manual"])
    if motor == "refinado":
        return motor_match_refinado(
            ba, rn_universo, mostrar_progreso=verbose, **cfg.params_motores["refinado"]
        )
    raise KeyError(f"Motor desconocido: {motor!r}. Disponibles: estandar, manual, refinado.")


def _normalizar(res: pd.DataFrame | None, motor: str, index) -> pd.DataFrame:
    """Lleva el resultado de un motor al universo COMPLETO de BANCI.

    Un motor puede haber visto menos filas (por el filtro de no localizados o por
    ser un eslabón de la cadena). Las que no vio no son 'sin evaluar': para el
    resto del pipeline son `sin_match`, que es justo lo que la cascada espera.
    """
    col_tipo, col_id = f"tipo_match_{motor}", f"id_match_{motor}"
    if res is None:
        return pd.DataFrame({col_tipo: "sin_match", col_id: None}, index=index)
    res = res.reindex(index)
    res[col_tipo] = res[col_tipo].fillna("sin_match")
    if f"score_{motor}" in res.columns:
        res[f"score_{motor}"] = res[f"score_{motor}"].fillna(0)
    return res


def _n_match(df: pd.DataFrame, motor: str) -> int:
    return int((df[f"tipo_match_{motor}"] != "sin_match").sum())


# ─────────────────────────────────────────────────────────────────────────────
def _pegar(destino: pd.DataFrame, resultado: pd.DataFrame) -> pd.DataFrame:
    """Añade las columnas de un motor al acumulado, en un solo concat.

    Columna por columna (`for col: destino[col] = ...`) fragmenta el DataFrame
    y dispara PerformanceWarning con ~30 columnas por motor.
    """
    nuevas = [c for c in resultado.columns if c not in destino.columns]
    solapadas = [c for c in resultado.columns if c in destino.columns]
    if solapadas:
        destino = destino.copy()
        for c in solapadas:
            destino[c] = resultado[c]
    if nuevas:
        destino = pd.concat([destino, resultado[nuevas]], axis=1)
    return destino


# Clasificaciones del RNPDNO que pertenecen al universo de match, por PREFIJO y sin
# acentos: el dato llega como "Desaparecidos" / "DESAPARECIDA" / "Desaparecido" y
# comparar el literal completo dejaría fuera variantes que son lo mismo.
# Es la lista CLASIF_UNIVERSO de normalizar_folios_v6.py, con su misma advertencia:
# va "NO LOCALIZAD" y NUNCA "LOCALIZAD" a secas, porque son opuestos y uno contiene
# al otro. El prefijo salva la ambigüedad ("NO LOCALIZADA" no empieza con "LOCALIZAD").
CLASIF_UNIVERSO = ("DESAPARECID", "PENDIENTE", "NO LOCALIZAD")


def _universo_rnpdno(rn: pd.DataFrame, cfg: Settings, verbose: bool = True) -> pd.DataFrame:
    """El universo del RNPDNO que los motores manual y refinado pueden reclamar.

    Por defecto: desaparecidos/pendientes del sexenio. Dos perillas del perfil lo
    abren:

      filtrar_rnpdno_clasificacion = false  → entran también los LOCALIZADOS
      fecha_sexenio = "1900-01-01"          → entra todo el histórico

    Con las dos abiertas el universo es el RNPDNO completo (cruce total). Es un
    universo más ancho, no un criterio más laxo: los guardianes anti-homónimo de
    cada motor siguen decidiendo qué par se acepta.

    Las fechas nulas se incluyen (no se puede descartar que caigan en rango); v6 las
    descarta, pero hoy no hay ninguna y mantenerlas no puede encoger el universo en
    silencio si un corte futuro las trae.
    """
    corte = pd.Timestamp(cfg.fecha_sexenio, tz="UTC")
    col_clasif = _primera(rn, ["clasificacion_des_derivada_rnpdno", "clasificacion_des"])
    col_fecha = columna_fecha_periodo(rn, verbose)

    mask = pd.Series(True, index=rn.index)
    if not cfg.filtrar_rnpdno_clasificacion:
        col_clasif = None
        if verbose:
            print("  🔓 filtrar_rnpdno_clasificacion=false: los LOCALIZADOS del RNPDNO "
                  "entran al universo de match.")
    if col_clasif:
        norm = rn[col_clasif].fillna("").astype(str).map(
            lambda x: unicodedata.normalize("NFD", x).encode("ascii", "ignore")
                                 .decode("ascii").upper().strip()
        )
        dentro = norm.str.startswith(CLASIF_UNIVERSO)
        # Una clasificación nueva que debería entrar y no está en la lista se
        # excluiría en silencio: aquí se ve.
        if verbose:
            fuera = norm[~dentro].value_counts()
            for etiqueta, n in fuera.items():
                if not str(etiqueta).startswith("LOCALIZAD"):
                    print(f"  ⚠️ clasificación '{etiqueta or '(vacío)'}' ({n:,} registros) "
                          f"queda FUERA del universo de match. Si debe entrar, agrégala "
                          f"a CLASIF_UNIVERSO en src/pipeline/motores.py.")
        mask &= dentro
    if col_fecha:
        dt = pd.to_datetime(rn[col_fecha], errors="coerce", utc=True)
        mask &= (dt >= corte) | dt.isna()
    return rn[mask].copy()


def _banci_no_localizados(ba: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    """BANCI sin los localizados (equivale a FILTRAR_SOLO_NO_LOCALIZADOS de v6).

    Un localizado puede casar con un desaparecido del RNPDNO vía folio y generar
    matches espurios; además ya no necesita búsqueda.
    """
    col = "localizado_o_no_localizado_derivada_banci"
    v = ba[col].fillna("").astype(str).map(
        lambda x: unicodedata.normalize("NFD", x).encode("ascii", "ignore").decode("ascii").upper().strip()
    )
    return ba[v.str.startswith("NO") | (v == "")].copy()


def _primera(df: pd.DataFrame, candidatas: list[str]) -> str | None:
    return next((c for c in candidatas if c in df.columns), None)
