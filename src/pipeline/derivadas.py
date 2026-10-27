"""CAPA B · Banderas derivadas y curación de columnas.

Traduce el universo crudo a las banderas booleanas del catálogo de abreviaturas
(`is_des`, `is_ccarp`, `is_dfor`, …) y a las dos columnas sobre las que se
rebana: `fecha_dt` y `cve_ent`.

`cve_ent` es la pieza clave del cambio de arquitectura: la entidad dejó de
filtrarse ANTES del matching y ahora viaja como columna, de modo que una sola
corrida de motores sirve para las 32 PPT estatales.

El resultado se guarda con sólo las columnas que el rebanado y las PPT
consumen, y con las categóricas convertidas: el RNPDNO pasa de 67 columnas
mayormente `object` a un frame varias veces más pequeño en memoria.
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

import config
from src.pipeline.reglas import aplicar_reglas_rnpdno
from src.settings import Settings

# Versión del esquema de esta capa. SÚBELA al cambiar las banderas `is_*`, las
# columnas conservadas o la lógica de derivación: entra en `clave_universo`. El
# caché no depende de que se suba: su llave ya incluye el código de la capa
# (`huella.huella_codigo`).
VERSION_DERIVADAS = 27

# ── Columnas conservadas en el universo ──────────────────────────────────────
# Todo lo que no esté aquí (ni sea una bandera is_*) se descarta: las columnas
# duplicadas del ETL (`*_rnpdno`, `*_banci`) triplican el peso sin aportar nada
# al rebanado ni a las PPT.
COLS_RN = [
    "fub_rnpdno",
    # El expediente tal como viene: el folio que juzgan `cfval`/`cfvac`. Viaja
    # para que lo lleve toda base exportada; los entregables lo piden.
    "expedientes_rnpdno",
    "sexo_rnpdno", "fechanacimiento_derivada_rnpdno",
    "idmunicipio_derivada_rnpdno", "clasificacion_des_derivada_rnpdno",
    # La dependencia que corrigió actualizar_rn_con_banci; sin esa regla, la del
    # RNPDNO (sólo entra una de las dos, ver derivar_rnpdno).
    "dependencia_origen_derivada_rnpdno_banci", "dependencia_origen_rnpdno",
    "fecha_hechos_modificada_derivada_rnpdno",
    # La fecha de hechos SIN RELLENAR, la única que conserva los huecos:
    # `fecha_hechos_modificada_derivada_rnpdno` los rellena con percato/captura y
    # llega sin un solo nulo. Es lo que cuenta el marcador `_sfdes` (notebook 5).
    "fechahechos_derivada_rnpdno",
    # Captura y localización: las exporta el notebook 4. `fechalocaliza` sólo la
    # traen los localizados, así que en las rebanadas `_des` sale nula al 100%.
    "fechacaptura_derivada_rnpdno", "fechalocaliza_derivada_rnpdno",
    # Validez de la CURP imputada; el rebanado la lee como `ccurp` (BANDERAS_ETL).
    "curp_vic_valida_derivada_rnpdno",
    # Los tres campos del nombre tal como vienen: los cuenta `snomb` (notebook 5).
    "nombre_vic_rnpdno", "primerapellido_vic_rnpdno", "segundoapellido_vic_rnpdno",
    "idestado_derivada_rnpdno",
]
COLS_BA = [
    "sexo_banci", "id_mun_hchos_banci", "localizado_o_no_localizado_derivada_banci",
    # La fecha que rebana el período en BANCI (DIMENSIONES).
    "fha_de_hchos_derivada_banci",
    # El FUB con que se cruzó cada fila y los motores que lo sostienen.
    "fub_derivada_rnpdno_banci", "tipo_match_derivada_rnpdno_banci",
    # Validez de la CURP de BANCI; el rebanado la lee como `ccurp`.
    "curp_valida_derivada_banci",
    # Los FUB extra de un registro con varias parejas confirmadas a mano.
    "fubs_confirmados_manual_derivada_rnpdno_banci",
]
# Baja cardinalidad sobre cientos de miles de filas → categoría.
CATEGORICAS = [
    "sexo_rnpdno", "sexo_banci", "clasificacion_des_derivada_rnpdno",
    "estatus_loc_derivada_rnpdno", "estatus_loc_derivada_banci",
    "nombre_entidad_derivada_rnpdno", "nombre_entidad_derivada_banci",
    "estado_final_nuevo",
    "dependencia_origen_derivada_rnpdno_banci", "dependencia_origen_rnpdno",
    "tipo_match_derivada_rnpdno_banci",
    "localizado_o_no_localizado_derivada_banci",
]

# Banderas que NO se guardan porque son la negación exacta de otra: el rebanado
# las resuelve al filtrar negando la guardada, así cada partición vive en una
# sola columna. Sólo entran parejas que son complemento POR CONSTRUCCIÓN, en rn
# y en ba. `cvid`/`svid` NO lo son: un desaparecido no es ninguna de las dos.
NEGACIONES = {
    "sdel": "cdel", "sind": "cind", "scurp": "ccurp",
    "cisf": "sisf", "sfvac": "cfvac", "sfval": "cfval",
}

# Banderas que en una base son constantes por construcción: no se guardan, el
# rebanado devuelve el valor directamente. Todo registro de BANCI es una carpeta
# de fiscalía con registro administrativo y folio.
CONSTANTES = {
    "rn": {},
    "ba": {"cind": True, "cfval": True, "cfvac": False,
           "fis": True, "com": False, "por": False},
}

# Columnas con que el rebanado y los notebooks leen cada dimensión, por base.
# En el RNPDNO la fecha y la clave de entidad son columnas del ETL; no se copian.
DIMENSIONES = {
    "rn": {"fecha": "fecha_hechos_modificada_derivada_rnpdno",
           "cve_ent": "idestado_derivada_rnpdno",
           "entidad": "nombre_entidad_derivada_rnpdno",
           "estatus_loc": "estatus_loc_derivada_rnpdno"},
    "ba": {"fecha": "fha_de_hchos_derivada_banci",
           "cve_ent": "cve_entidad_derivada_banci",
           "entidad": "nombre_entidad_derivada_banci",
           "estatus_loc": "estatus_loc_derivada_banci"},
}


def columna_dimension(nombre_frame: str, dimension: str) -> str:
    """Resuelve la columna de entidad según el interruptor de presentación actual."""
    if nombre_frame == "rn" and config.USAR_ESTADO_EXTRAIDO_EN_PRESENTACIONES:
        columnas_estado_extraido = {
            "cve_ent": "idestado_final_nuevo",
            "entidad": "estado_final_nuevo",
        }
        if dimension in columnas_estado_extraido:
            return columnas_estado_extraido[dimension]
    return DIMENSIONES[nombre_frame][dimension]


# Banderas que ya vienen calculadas del ETL: el rebanado las lee en su columna
# en vez de copiarlas a una `is_*`.
BANDERAS_ETL = {
    "rn": {"ccurp": "curp_vic_valida_derivada_rnpdno"},
    "ba": {"ccurp": "curp_valida_derivada_banci"},
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).upper().strip()


def _normalizar_nombre_estado(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", _norm(texto)).strip()


_ALIAS_ESTADO_ID = {
    _normalizar_nombre_estado(nombre): id_estado
    for id_estado, nombre in config.ENTIDADES.items()
    if 1 <= id_estado <= 32
}
_ALIAS_ESTADO_ID.update({
    "ESTADO DE MEXICO": 15,
    "EDOMEX": 15,
    "CIUDAD DE MEXICO": 9,
    "CDMX": 9,
    "DISTRITO FEDERAL": 9,
    "D F": 9,
    "COAHUILA DE ZARAGOZA": 5,
    "MICHOACAN DE OCAMPO": 16,
    "VERACRUZ DE IGNACIO DE LA LLAVE": 30,
})
_ESTADO_FINAL_RE = re.compile(
    r"(?:^| )(" + "|".join(
        re.escape(alias)
        for alias in sorted(_ALIAS_ESTADO_ID, key=len, reverse=True)
    ) + r")$"
)


def _resolver_estado_extraido(
    dependencia: pd.Series, idestado: pd.Series
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Devuelve estado final, coincidencia textual y respaldo por ID."""
    dependencia_norm = dependencia.astype("string").fillna("").map(
        _normalizar_nombre_estado
    )
    alias_final = dependencia_norm.str.extract(_ESTADO_FINAL_RE, expand=False)
    id_texto = alias_final.map(_ALIAS_ESTADO_ID)
    estado_texto = id_texto.map(config.ENTIDADES).astype("object")

    ids = pd.to_numeric(idestado, errors="coerce")
    ids_validos = ids.where(ids.between(1, 32) & ids.mod(1).eq(0))
    estado_id = ids_validos.astype("Int64").map(config.ENTIDADES).astype("object")

    return estado_texto.combine_first(estado_id), estado_texto, estado_id


# Nombre normalizado de entidad → clave INEGI, con los alias que usa BANCI.
_MAPA_ENTIDAD = {_norm(v): k for k, v in config.ENTIDADES.items()}
_MAPA_ENTIDAD.update({
    "ESTADO DE MEXICO": 15, "MEXICO": 15, "EDOMEX": 15,
    "DISTRITO FEDERAL": 9, "CDMX": 9,
    "COAHUILA DE ZARAGOZA": 5, "MICHOACAN DE OCAMPO": 16,
    "VERACRUZ DE IGNACIO DE LA LLAVE": 30,
})


def _id_estado_extraido(estado: pd.Series) -> pd.Series:
    estado_norm = estado.astype("string").map(_normalizar_nombre_estado)
    return estado_norm.map(_MAPA_ENTIDAD).astype("Int8")


def columna_bandera(df: pd.DataFrame, token: str) -> str:
    """La columna guardada de la bandera `token`: `is_<token>_derivada_<fuentes>`."""
    cols = [c for c in df.columns if c.startswith(f"is_{token}_derivada_")]
    if len(cols) != 1:
        raise KeyError(f"Bandera '{token}': {len(cols)} columnas {cols}")
    return cols[0]


def _primera(df: pd.DataFrame, candidatas: list[str]):
    return next((c for c in candidatas if c in df.columns), None)


def _serie_txt(df: pd.DataFrame, col: str | None) -> pd.Series:
    """Serie de texto en minúsculas, tolerante a columna ausente o categórica."""
    if col is None or col not in df.columns:
        return pd.Series("", index=df.index, dtype="object")
    s = df[col]
    if isinstance(s.dtype, pd.CategoricalDtype):
        s = s.astype("object")
    return s.fillna("").astype(str).str.lower()


# Columna de fecha de hechos con la que se acota el PERÍODO, en orden de preferencia.
#
# Es la advertencia de normalizar_folios_v6.py: hay dos fechas de hechos y NO son la
# misma. La "modificada" es la ya depurada y es la que define el universo; la cruda
# (`fechahechos`) difiere en decenas de miles de filas y mueve registros de un lado a
# otro del corte del sexenio sin que nada falle. Por eso la lista NUNCA incluye la
# cruda: si ninguna "modificada" existe, es preferible fallar a filtrar mal.
COLS_FECHA_PERIODO = [
    "fecha_hechos_modificada_derivada_rnpdno",
]


def columna_fecha_periodo(rn: pd.DataFrame, verbose: bool = True) -> str:
    """Resuelve con qué columna se acota el período, y avisa si las candidatas
    presentes NO coinciden entre sí (hoy son idénticas; si un corte futuro las
    separa, el filtro cambiaría de significado en silencio)."""
    presentes = [c for c in COLS_FECHA_PERIODO if c in rn.columns]
    if not presentes:
        raise KeyError(
            "No hay ninguna columna de fecha de hechos MODIFICADA en el RNPDNO "
            f"({COLS_FECHA_PERIODO}). Sin ella el corte del sexenio se haría con la "
            "fecha cruda, que no es la misma. Vuelve a correr el ETL del notebook 1."
        )
    elegida = presentes[0]
    if verbose and len(presentes) > 1:
        base = pd.to_datetime(rn[elegida], errors="coerce")
        for otra in presentes[1:]:
            n = int((pd.to_datetime(rn[otra], errors="coerce") != base).sum())
            if n:
                print(f"  ⚠️ '{otra}' difiere de '{elegida}' en {n:,} filas. Se usa "
                      f"'{elegida}' para acotar el período; revisa cuál es la buena.")
    return elegida


# ─────────────────────────────────────────────────────────────────────────────
def derivar_rnpdno(rn: pd.DataFrame, fubs: set[str], mapa_tipo_match: dict,
                   cfg: Settings, verbose: bool = True) -> pd.DataFrame:
    """RNPDNO con banderas y dimensiones de rebanado (ver DIMENSIONES)."""
    rn = aplicar_reglas_rnpdno(rn, fubs, cfg, verbose=verbose)
    out = pd.DataFrame(index=rn.index)

    col_fub = "fub_rnpdno"
    fub_txt = rn[col_fub].astype(str)

    out["in_banci_derivada_rnpdno_banci"] = fub_txt.isin(fubs).to_numpy()
    out["tipo_match_derivada_rnpdno_banci"] = fub_txt.map(mapa_tipo_match).fillna("sin_match")

    # La fecha que rebana el período es la del ETL (DIMENSIONES); aquí sólo se
    # verifica que las candidatas coincidan.
    columna_fecha_periodo(rn, verbose)

    # ── Entidad como DIMENSIÓN, no como filtro previo ───────────────────────
    # La clave es `idestado_derivada_rnpdno`, que ya viaja en COLS_RN: no se copia.
    cve = pd.to_numeric(rn["idestado_derivada_rnpdno"], errors="coerce").astype("Int8")
    out["nombre_entidad_derivada_rnpdno"] = cve.map(config.ENTIDADES)

    col_dependencia_estado = _primera(
        rn,
        ["dependencia_origen_derivada_rnpdno_banci", "dependencia_origen_rnpdno"],
    )
    dependencia_estado = (
        rn[col_dependencia_estado]
        if col_dependencia_estado is not None
        else pd.Series(pd.NA, index=rn.index, dtype="object")
    )
    if (
        col_dependencia_estado == "dependencia_origen_derivada_rnpdno_banci"
        and "dependencia_origen_rnpdno" in rn.columns
    ):
        dependencia_estado = dependencia_estado.astype("string")
        dependencia_original = rn["dependencia_origen_rnpdno"].astype("string")
        dependencia_no_vacia = (
            dependencia_estado.str.strip().ne("").fillna(False)
        )
        dependencia_estado = dependencia_estado.where(
            dependencia_no_vacia, dependencia_original
        )

    col_idestado = _primera(rn, ["idestado_derivada_rnpdno", "idestado"])
    ids_estado = (
        rn[col_idestado]
        if col_idestado is not None
        else pd.Series(pd.NA, index=rn.index, dtype="object")
    )
    estado_final, estado_texto, estado_respaldo = _resolver_estado_extraido(
        dependencia_estado, ids_estado
    )
    out["estado_final_nuevo"] = estado_final
    out["idestado_final_nuevo"] = _id_estado_extraido(estado_final)

    if verbose:
        total = len(rn)
        desde_texto = int(estado_texto.notna().sum())
        desde_respaldo = int((estado_texto.isna() & estado_respaldo.notna()).sum())
        sin_resolver = int(estado_final.isna().sum())
        inconsistente = (
            estado_texto.notna()
            & estado_respaldo.notna()
            & estado_texto.ne(estado_respaldo)
        )

        def porcentaje(cantidad: int) -> float:
            return 100 * cantidad / total if total else 0.0

        print(
            "  Estado extraído: "
            f"texto {desde_texto:,} ({porcentaje(desde_texto):.1f}%), "
            f"respaldo idestado {desde_respaldo:,} ({porcentaje(desde_respaldo):.1f}%), "
            f"sin resolver {sin_resolver:,} ({porcentaje(sin_resolver):.1f}%)."
        )
        print("  Distribución final por estado:")
        print(
            estado_final.value_counts(dropna=False, sort=False)
            .rename_axis("estado_final_nuevo")
            .rename("registros")
            .to_string()
        )
        if inconsistente.any():
            print(
                f"  ⚠️ Estado de dependencia distinto a idestado en "
                f"{int(inconsistente.sum()):,} registros; se conserva el estado del texto."
            )
            ejemplos = pd.DataFrame({
                "dependencia": dependencia_estado,
                "estado_texto": estado_texto,
                "estado_id": estado_respaldo,
            }).loc[inconsistente].head(5)
            print(ejemplos.to_string(index=False))

    col_clasif = _primera(rn, ["clasificacion_des_derivada_rnpdno", "clasificacion_des"])
    out["estatus_loc_derivada_rnpdno"] = rn[col_clasif].map(
        {"Localizados": "loc", "Desaparecidos": "des", "Pendientes": "des"}
    ).fillna("des")

    est = _serie_txt(rn, "estatus_rnpdno")
    out["is_cvid_derivada_rnpdno"] = est.str.contains("con vida", na=False).to_numpy()
    out["is_svid_derivada_rnpdno"] = est.str.contains("sin vida", na=False).to_numpy()

    col_delito = "delitolocalizacion_rnpdno"
    delito = _serie_txt(rn, col_delito)
    out["is_cdel_derivada_rnpdno"] = (delito.str.strip() != "").to_numpy()
    # Con `propagar_delito_banci` los matcheados toman el tipo de BANCI.
    sfx = "derivada_rnpdno_banci" if cfg.propagar_delito_banci else "derivada_rnpdno"
    out[f"is_dfor_{sfx}"] = delito.str.contains("forzada", regex=True).to_numpy()
    out[f"is_cpar_{sfx}"] = delito.str.contains("particular", regex=True).to_numpy()

    ind = _serie_txt(rn, "indicadora_indicio_de_vida_derivada_pui").str.strip()
    out["is_cind_derivada_pui"] = (ind != "sin registro administrativo").to_numpy()

    curp_ok = rn["curp_vic_valida_derivada_rnpdno"].fillna(False).astype(bool).to_numpy()
    # `sisf` = SIN INFORMACIÓN SUFICIENTE: ni CURP válida ni registro
    # administrativo en PUI. Antes se llamaba `sdat` ("sin datos"), nombre que
    # se confundía con los faltantes de campo (`scurp`, `smuni`, `sfnac`, …).
    out["is_sisf_derivada_rnpdno_pui"] = ~curp_ok & ~out["is_cind_derivada_pui"]
    # `cisf` es el COMPLEMENTO exacto de `sisf` (el rebanado lo resuelve negando
    # `is_sisf`, ver NEGACIONES): basta una de las dos fuentes
    # (CURP válida o registro en PUI) para que el registro sea identificable.
    #   cisf = ~(~ccurp & sind) = ccurp | cind
    # Cruzado con la partición cind/sind se reparte en dos ramas que suman cisf:
    #   cisf_cind = cind            (todo `cind` es, por definición, `cisf`)
    #   cisf_sind = ccurp & sind    (sin indicios, pero identificable por CURP)
    # El rebanado las arma solo, combinando banderas: subfiltro="cisf_cind".

    # ── Folio válido: el expediente pasa el criterio de Carpeta de Investigación
    # que elija `MODALIDAD_CLASIFICACION_CARPETA` (o el perfil):
    #   modalidad 1 → RNPDNO_REGEX_CARPETA, un solo patrón nacional. Es una
    #                 búsqueda de token (\bAP\b, \bCI\b, \bCDI\b), no una
    #                 validación de formato: `cfval` pasa a significar "el
    #                 expediente menciona una carpeta".
    #   modalidad 2 → CATALOGO_REGEX_CI_POR_ENTIDAD, un patrón por entidad.
    #                 `cfval` significa "el folio cumple el formato de su estado".
    #   modalidad 3 → CATALOGO_REGEX_CI_POR_ENTIDAD_2, igual que la 2; en Oaxaca
    #                 además las siglas del folio deben estar en NOMENCLATURAS_OAXACA.
    #   modalidad 4 → CATALOGO_REGEX_CI_POR_ENTIDAD_3, unión de los catálogos de la
    #                 2 y la 3; pasa lo que pase en cualquiera de las dos.
    # Con `MODALIDAD_MANUAL_CLASIFICACION_CARPETA` (o el perfil) se suman todos los
    # FUBs de la revisión manual de CARPETAS_MANUALES_DIR, pasen o no el criterio de
    # la modalidad y aunque su expediente venga vacío. Sólo agrega carpetas.
    # Las dos lecturas son legítimas pero NO son la misma; el nombre del
    # indicador no lo dice, así que conviene anotar la modalidad en la lámina.
    # La modalidad entra en `clave_universo`, de modo que cambiarla invalida el
    # caché y recalcula estas banderas.
    # `cfval` y `sfval` son una PARTICIÓN del universo: cfval + sfval = total.
    #   cfval → hay folio y pasa el criterio de la modalidad, o la revisión
    #           manual lo da por válido
    #   sfval → todo lo demás, sea porque el folio no cumple el criterio o porque
    #           el campo de expediente viene vacío
    # `cfvac`/`sfvac` son otra partición, transversal: dice si el campo trae
    # texto, no si ese texto es válido. Cruzada con la anterior parte `sfval`
    # en las dos ramas que consumen las plantillas:
    #   sfval_sfvac → hay folio capturado, pero no pasa el criterio
    #   sfval_cfvac → el campo viene vacío o nulo (no hay folio que juzgar)
    # y sfval_sfvac + sfval_cfvac = sfval. Un expediente vacío que la revisión
    # manual da por válido cae en `cfval`, así que ahí `cfvac` ya no implica `sfval`:
    # las plantillas cuentan el vacío como `sfval_cfvac`, nunca como `cfvac` a secas.
    # No confundir `cfvac` (el campo de folio viene vacío) con `ccvac` (a la
    # persona le faltan campos de identificación).
    from src.cleaning import clasificar_carpeta, carpeta_validada_manual
    col_ent_rn = _primera(rn, ["idestado_derivada_rnpdno", "idestado"])
    if "expedientes_rnpdno" in rn.columns:
        vacio = rn["expedientes_rnpdno"].astype("object").fillna("").astype(str).str.strip().eq("").to_numpy()
        # La modalidad 1 no necesita la entidad; la 2, la 3 y la 4 sí, y sin ella no pueden
        # evaluar nada, así que se conserva el respaldo en ceros.
        usa_entidad = cfg.modalidad_clasificacion_carpeta != 1
        valido = (clasificar_carpeta(rn["expedientes_rnpdno"], rn[col_ent_rn],
                                     modalidad=cfg.modalidad_clasificacion_carpeta).to_numpy()
                  if col_ent_rn or not usa_entidad else np.zeros(len(rn), dtype=bool))
    else:
        vacio = np.ones(len(rn), dtype=bool)
        valido = np.zeros(len(rn), dtype=bool)
    manual = carpeta_validada_manual(rn["fub_rnpdno"],
                                     activa=cfg.modalidad_manual_clasificacion_carpeta,
                                     verbose=verbose).to_numpy()
    cfval = (valido & ~vacio) | manual
    if verbose and cfg.modalidad_manual_clasificacion_carpeta:
        print(f"     → {int((manual & ~(valido & ~vacio)).sum()):,} pasan a 'con carpeta' "
              f"({int((manual & vacio).sum()):,} con el expediente vacío); "
              f"{int((manual & valido & ~vacio).sum()):,} ya la tenían por la modalidad.")
    out["is_cfvac_derivada_rnpdno"] = vacio
    out["is_cfval_derivada_rnpdno"] = cfval

    col_dep = _primera(rn, ["dependencia_origen_derivada_rnpdno_banci", "dependencia_origen_rnpdno"])
    dep = _serie_txt(rn, col_dep)
    sfx = "derivada_rnpdno_banci" if col_dep.endswith("_rnpdno_banci") else "derivada_rnpdno"
    out[f"is_fis_{sfx}"] = dep.str.contains(r"fiscalia|fiscalía|procuradur|subprocuradur", regex=True).to_numpy()
    out[f"is_com_{sfx}"] = dep.str.contains(r"comision|comisión", regex=True).to_numpy()
    out[f"is_por_{sfx}"] = ~(out[f"is_fis_{sfx}"] | out[f"is_com_{sfx}"])

    # De la dependencia sólo entra una: la corregida por el cruce, si la regla corrió.
    cols = [c for c in COLS_RN if not (c == "dependencia_origen_rnpdno"
                                       and "dependencia_origen_derivada_rnpdno_banci" in rn.columns)]
    return _ensamblar(rn, out, cols, verbose, "RNPDNO")


def derivar_banci(ba: pd.DataFrame, rn_derivado: pd.DataFrame,
                  cfg: Settings, verbose: bool = True) -> pd.DataFrame:
    """BANCI con banderas y dimensiones de rebanado (ver DIMENSIONES)."""
    out = pd.DataFrame(index=ba.index)

    out["in_rnpdno_derivada_rnpdno_banci"] = (ba["tipo_match_derivada_rnpdno_banci"] != "sin_match").to_numpy()

    col_ent = "entidad_derivada_banci"
    ent_norm = ba[col_ent].fillna("").astype(str).map(_norm)
    out["cve_entidad_derivada_banci"] = ent_norm.map(_MAPA_ENTIDAD).astype("Int8")
    out["nombre_entidad_derivada_banci"] = out["cve_entidad_derivada_banci"].map(config.ENTIDADES)
    if verbose:
        sin_ent = int(out["cve_entidad_derivada_banci"].isna().sum())
        if sin_ent:
            faltantes = sorted(ent_norm[out["cve_entidad_derivada_banci"].isna()].unique())[:5]
            print(f"  ⚠️ BANCI: {sin_ent:,} registros sin clave de entidad. Ejemplos: {faltantes}")

    loc = _serie_txt(ba, "localizado_o_no_localizado_derivada_banci")
    es_loc = loc.str.contains("localiza", na=False) & ~loc.str.contains("no localiza", na=False)
    out["estatus_loc_derivada_banci"] = np.where(es_loc, "loc", "des")

    # Estado de vida: el de BANCI, salvo en los matcheados (abajo), donde manda el RNPDNO.
    out["is_cvid_derivada_rnpdno_banci"] = es_loc.to_numpy()
    out["is_svid_derivada_rnpdno_banci"] = np.zeros(len(ba), dtype=bool)

    fue_delito = _serie_txt(ba, "fue_delito_banci")
    out["is_cdel_derivada_banci"] = fue_delito.str.contains("delito|sí|si|1", regex=True).to_numpy()

    # cind, cfval, cfvac, fis, com y por son constantes en BANCI: ver CONSTANTES.

    delito = _serie_txt(ba, "delito_hom_banci")
    out["is_dfor_derivada_banci"] = delito.str.contains("forzada", regex=True).to_numpy()
    out["is_cpar_derivada_banci"] = delito.str.contains("particular", regex=True).to_numpy()

    # Sin información suficiente: nunca en BANCI; en los matcheados, la del RNPDNO.
    out["is_sisf_derivada_rnpdno_banci_pui"] = np.zeros(len(ba), dtype=bool)

    # Para los matcheados, el estado de vida y la falta de datos los manda el RNPDNO.
    if not rn_derivado.empty:
        rn_idx = rn_derivado.drop_duplicates(subset=["fub_rnpdno"]).set_index("fub_rnpdno")
        mask = out["in_rnpdno_derivada_rnpdno_banci"] & ba["fub_derivada_rnpdno_banci"].notna()
        fubs = ba.loc[mask, "fub_derivada_rnpdno_banci"].astype(str)
        for token in ("cvid", "svid", "sisf"):
            bandera = columna_bandera(out, token)
            valores = fubs.map(rn_idx[columna_bandera(rn_idx, token)])
            out.loc[mask, bandera] = valores.fillna(out.loc[mask, bandera]).astype(bool)

    return _ensamblar(ba, out, COLS_BA, verbose, "BANCI")


# ─────────────────────────────────────────────────────────────────────────────
def _ensamblar(origen: pd.DataFrame, derivadas: pd.DataFrame,
               cols_base: list[str], verbose: bool, etiqueta: str) -> pd.DataFrame:
    """Une columnas curadas del origen con las derivadas y optimiza dtypes."""
    presentes = [c for c in cols_base if c in origen.columns and c not in derivadas.columns]
    df = pd.concat([origen[presentes], derivadas], axis=1)

    # Banderas siempre bool (no object): 1 byte por fila en vez de 8 + puntero.
    # Incluye las que llegan del ETL: el rebanado las niega con `~`, que sobre
    # un object de Python daría -1/-2 en vez de False/True.
    del_etl = {c for m in BANDERAS_ETL.values() for c in m.values()}
    for c in df.columns:
        if c.startswith(("is_", "in_banci_", "in_rnpdno_")) or c in del_etl:
            df[c] = df[c].fillna(False).astype(bool)

    antes = df.memory_usage(deep=True).sum()
    for c in CATEGORICAS:
        if c in df.columns and not isinstance(df[c].dtype, pd.CategoricalDtype):
            df[c] = df[c].astype("category")
    despues = df.memory_usage(deep=True).sum()

    if verbose:
        orig = origen.memory_usage(deep=True).sum()
        print(f"  📦 {etiqueta}: {len(origen.columns)} cols / {orig/1e6:.0f} MB "
              f"→ {len(df.columns)} cols / {despues/1e6:.0f} MB "
              f"(categóricas: −{(antes-despues)/1e6:.0f} MB)")
    return df.reset_index(drop=True)


def propagar_delito_desde_banci(rn: pd.DataFrame, ba: pd.DataFrame,
                                verbose: bool = True) -> pd.DataFrame:
    """Toma de BANCI el tipo de desaparición para los registros matcheados.

    `delitolocalizacion` del RNPDNO sólo se llena cuando la persona es
    localizada: está vacío en el 100% de los desaparecidos. Por eso
    `is_dfor` / `is_cpar` calculados desde el RNPDNO son estructuralmente 0 para
    `estatus_loc == "des"`, y un indicador como `reg_rn-si-ba_01oct24-max_des_dfor`
    saldría siempre en cero.

    BANCI sí trae esa clasificación en `delito_hom` ("Desaparición forzada" /
    "Cometida por particulares"). Para los FUBs con match se adopta la de BANCI;
    los no matcheados conservan la del RNPDNO.
    """
    matched = ba[ba["in_rnpdno_derivada_rnpdno_banci"] & ba["fub_derivada_rnpdno_banci"].notna()]
    if matched.empty:
        return rn

    # Cada FUB apunta a la POSICIÓN de su fila de BANCI, para poder mapear varios
    # FUB a la misma fila. `fubs_confirmados_manual_derivada_rnpdno_banci` guarda las
    # parejas extra de un registro con más de una confirmación a mano: en
    # `fub_derivada_rnpdno_banci` sólo cabe
    # una, pero del lado del RNPDNO cada FUB es una persona distinta.
    # `motores.py` ya los reclama al construir `fubs_matcheados`, así que sin
    # expandirlos aquí quedaban dentro de `rn-si-ba` pero sin clasificación de
    # delito, y desaparecían del desglose dfor/cpar sin dejar rastro.
    fubs = list(matched["fub_derivada_rnpdno_banci"].astype(str))
    filas = list(range(len(matched)))
    if "fubs_confirmados_manual_derivada_rnpdno_banci" in matched.columns:
        for pos, lista in enumerate(matched["fubs_confirmados_manual_derivada_rnpdno_banci"]):
            if lista is None or (isinstance(lista, float) and pd.isna(lista)):
                continue
            for f in (p.strip() for p in str(lista).split(",")):
                if f:
                    fubs.append(f)
                    filas.append(pos)

    cols = {t: (columna_bandera(rn, t), columna_bandera(ba, t)) for t in ("dfor", "cpar")}
    antes = {t: int(rn[c_rn].sum()) for t, (c_rn, _) in cols.items()}
    fub_rn = rn["fub_rnpdno"].astype(str)

    for t, (bandera, bandera_ba) in cols.items():
        # Los primarios se añadieron antes que los extra, así que `keep="first"`
        # les da precedencia si un FUB aparece en las dos listas.
        mapa = pd.Series(matched[bandera_ba].to_numpy()[filas], index=fubs)
        mapa = mapa[~mapa.index.duplicated(keep="first")]
        valores = fub_rn.map(mapa)
        rn[bandera] = valores.fillna(rn[bandera]).astype(bool)

    if verbose:
        n_extra = len(fubs) - len(matched)
        for t, (c, _) in cols.items():
            print(f"  ↻ delito desde BANCI · {c}: {antes[t]:,} → {int(rn[c].sum()):,}")
        if n_extra:
            print(f"     (mapa de {len(mapa):,} FUB; {n_extra:,} vinieron de "
                  f"`fubs_confirmados_manual_derivada_rnpdno_banci`)")
    return rn
