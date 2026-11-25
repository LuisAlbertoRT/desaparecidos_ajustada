"""Directorio de indicios de vida: cuántos ya se formalizaron como localización.

Alimenta las láminas de la Estrategia de Búsqueda Generalizada del reporte
diario —la de las 24 entidades participantes y la de las 32 entidades—, cuyos
marcadores llevan el token `fmz` (formalizados).

Vive aparte de src/utils.py a propósito: `src.pipeline.universo` importa
`src.utils`, así que ese archivo entra en la huella de código de las dos capas
del caché (`huella.RAICES`) y editarlo obliga a repetir el matching. Nada del
pipeline importa este módulo: tocarlo no invalida el caché.
"""

import pandas as pd

import config
from src.validacion import leer_excel, resolver_columnas

# ── Imputación de entidad (lámina de las 32 con entidad imputada) ────────────
# Cascada para los registros del directorio SIN entidad de desaparición válida
# (vacía, 33 o "Nacido en el extranjero"), cruzando por FUB:
#   1. `nombre_entidad_derivada_rnpdno`  (universo RNPDNO: las columnas de
#      reg_rn_min-max.parquet)
#   2. `estado_final_nuevo`              (misma base)
#   3. la entidad de `curp_vic`          (Parquet crudo del RNPDNO), posiciones
#      12-13 de la CURP según el catálogo RENAPO.
# Estas constantes viven aquí y no en config.py a propósito: config entra en la
# llave del caché del pipeline (`huella_config`) y agregar una constante allá
# invalidaría el caché y repetiría el matching.
IMPUTACION_RN_FILE = config.RESULTADOS_INDICADORES_DIR / "reg_rn_min-max.parquet"
IMPUTACION_RN_COLUMNAS = ("nombre_entidad_derivada_rnpdno", "estado_final_nuevo")
IMPUTACION_CURP_FILE = config.RNPDNO_MANUAL_DIR / "reporte_personas_completo.parquet"

# Código RENAPO (posiciones 12-13 de la CURP) → entidad de config.ENTIDADES.
# "NE" (nacido en el extranjero) queda fuera a propósito: no imputa entidad.
CURP_ENTIDAD = {
    "AS": "Aguascalientes", "BC": "Baja California", "BS": "Baja California Sur",
    "CC": "Campeche", "CL": "Coahuila", "CM": "Colima", "CS": "Chiapas",
    "CH": "Chihuahua", "DF": "Ciudad de México", "DG": "Durango",
    "GT": "Guanajuato", "GR": "Guerrero", "HG": "Hidalgo", "JC": "Jalisco",
    "MC": "México", "MN": "Michoacán", "MS": "Morelos", "NT": "Nayarit",
    "NL": "Nuevo León", "OC": "Oaxaca", "PL": "Puebla", "QT": "Querétaro",
    "QR": "Quintana Roo", "SP": "San Luis Potosí", "SL": "Sinaloa",
    "SR": "Sonora", "TC": "Tabasco", "TS": "Tamaulipas", "TL": "Tlaxcala",
    "VZ": "Veracruz", "YN": "Yucatán", "ZS": "Zacatecas",
}


def _entidad_valida(serie: pd.Series) -> pd.Series:
    """Normaliza nombres de entidad y deja <NA> lo que no sea una de las 32.

    Aplica los mismos renombres del directorio (`México` → `Estado de México`),
    así los valores imputados caben directo en el tabulado por entidad.
    """
    validas = {config.DIRECTORIO_INDICIOS_RENOMBRES.get(n, n)
               for clave, n in config.ENTIDADES.items() if clave <= 32}
    s = serie.astype("string[python]").str.strip().str.replace(r"\s+", " ", regex=True)
    s = s.replace(config.DIRECTORIO_INDICIOS_RENOMBRES)
    return s.where(s.isin(validas))


def _imputar_estado(fubs: pd.Series, comprimido: pd.DataFrame, col_fub: str,
                    verbose: bool = True) -> pd.Series:
    """Entidad imputada de cada FUB, o <NA> si la cascada no la resuelve.

    `fubs` son los FUB del directorio sin entidad válida (ya en mayúsculas);
    el resultado conserva su índice. Los pasos 1 y 2 salen de `comprimido`
    cuando trae las columnas (el universo en memoria es la misma base que
    reg_rn_min-max.parquet); si no, se leen de ese Parquet.
    """
    paso1, paso2 = IMPUTACION_RN_COLUMNAS
    sub = fubs.to_frame("fub")
    if all(c in comprimido.columns for c in IMPUTACION_RN_COLUMNAS):
        rn = comprimido[[col_fub, paso1, paso2]].rename(columns={col_fub: "fub"})
    else:
        rn = pd.read_parquet(IMPUTACION_RN_FILE,
                             columns=["fub_rnpdno", paso1, paso2]
                             ).rename(columns={"fub_rnpdno": "fub"})
    rn = rn.assign(fub=rn["fub"].astype(str).str.upper()).drop_duplicates("fub")
    # how="left" sobre un lado derecho sin duplicados conserva el orden y el
    # número de filas; al final se restaura el índice original de `fubs`.
    sub = sub.merge(rn, on="fub", how="left")

    imputado = _entidad_valida(sub[paso1])
    n1 = int(imputado.notna().sum())
    imputado = imputado.fillna(_entidad_valida(sub[paso2]))
    n2 = int(imputado.notna().sum()) - n1

    n3 = 0
    falta = imputado.isna()
    if falta.any() and IMPUTACION_CURP_FILE.exists():
        comp = pd.read_parquet(IMPUTACION_CURP_FILE, columns=["fub", "curp_vic"])
        comp["fub"] = comp["fub"].astype(str).str.upper()
        comp = comp.drop_duplicates("fub")
        sub = sub.merge(comp, on="fub", how="left")
        curp = sub["curp_vic"].astype("string").str.strip().str.upper()
        # Sólo CURP con formato válido; el código de estado sale de sus
        # posiciones 12-13 y "NE" no está en el mapa, así que no imputa.
        codigo = curp.where(curp.str.match(config.CURP_REGEX_FORMAT, na=False)).str[11:13]
        imputado = imputado.fillna(_entidad_valida(codigo.map(CURP_ENTIDAD)))
        n3 = int(imputado.notna().sum()) - n1 - n2
    elif falta.any() and verbose:
        print(f"     ⚠️ falta {IMPUTACION_CURP_FILE.name}: "
              "la CURP no imputa entidad en esta corrida.")

    if verbose:
        print(f"     entidad imputada: {n1 + n2 + n3:,} de {len(fubs):,} "
              f"(RNPDNO: {n1:,} · estado_final_nuevo: {n2:,} · CURP: {n3:,}; "
              f"sin resolver: {int(imputado.isna().sum()):,})")
    return imputado.set_axis(fubs.index)


def indicios_formalizados(comprimido, verbose: bool = True, imputar: bool = False):
    """Cuántos indicios de vida del directorio ya se formalizaron como localización.

    El directorio (`config.DIRECTORIO_INDICIOS_FILE`) es una foto congelada de las
    personas con indicio de vida a una fecha. Cruzarla contra el RNPDNO vigente
    responde: **de aquellos indicios, ¿a cuántos les siguió una localización?**
    De ahí el token `fmz` (formalizados) de los marcadores.

    No es una rebanada del universo y por eso no pasa por `Slice`: su población no
    sale del RNPDNO ni de BANCI, sino de un archivo externo, y su "período" es la
    fecha del corte, no un rango de fechas de hechos. Se inyecta como `extra=` en
    `Universo.indicadores`, igual que las diferencias contra el corte de marzo.

    Parameters
    ----------
    comprimido : DataFrame
        RNPDNO vigente. Debe traer las columnas de
        `config.DIRECTORIO_INDICIOS_COMPRIMIDO_COLUMN_MAPPING` (`fub` y la
        clasificación CRUDA `clasificacion_des_rnpdno`, no la derivada).
    verbose : bool
        Imprime el desglose y avisa de los FUB que no cruzan.
    imputar : bool
        Imputa la entidad SÓLO de los localizados sin entidad de desaparición
        válida (los del marcador `sisf`), con la cascada FUB →
        `nombre_entidad_derivada_rnpdno` → `estado_final_nuevo` → entidad de
        la CURP (`curp_vic`). Los todavía desaparecidos sin entidad no se
        tocan, así las barras de los demás estados no se mueven. Alimenta la
        lámina gemela de las 32 entidades con entidad imputada; `sin_estado`
        cuenta entonces sólo los localizados que NI ASÍ tienen entidad.

    Returns
    -------
    (tabulado, tabulado_32, conteos)
        `tabulado` tiene una fila por entidad y las columnas
        `estado_de_desaparicion`, `todavia_desaparecidos` y `localizados`,
        ordenada de mayor a menor por la primera. Es lo que dibuja la gráfica
        `gr_ent_*`. `tabulado_32` es la misma tabla pero con las 32 entidades
        federativas en vez de sólo las de la Búsqueda Generalizada: la dibuja
        `gr_32ent_*`. `conteos` trae los marcadores de las dos láminas:

        - `total`    : formalizados en `config.DIRECTORIO_INDICIOS_ESTADOS`,
                       las entidades de la Búsqueda Generalizada.
        - `nacional` : los mismos formalizados pero SIN acotar a esas
                       entidades, o sea el conteo en todo el país;
                       es el denominador de `pct`.
        - `pct`      : `total` / `nacional`, ya formateado ("92.8%"): qué
                       parte del total del país cae en esas entidades.
        - `resto`    : `nacional` − `total`, o sea los formalizados que caen
                       FUERA de esas entidades; alimenta el marcador `_v3`.
        - `universo` : personas del directorio en esas mismas entidades
                       (las dos series de la gráfica sumadas).
        - `universo_nacional` : total de personas del directorio, sin acotar
                                por entidad.
        - `total_32` : formalizados en las 32 entidades federativas, o sea
                       `nacional` sin lo que no es una entidad ("Nacido en el
                       extranjero"); alimenta los marcadores `_v2` y `_v4`,
                       o `_v2_v3` en la pasada con imputación.
        - `sin_estado`: registros localizados sin entidad federativa de
                        desaparición, que se excluyen del desglose por entidad.
    """
    directorio = leer_excel(
        config.DIRECTORIO_INDICIOS_FILE,
        config.DIRECTORIO_INDICIOS_COLUMN_MAPPING,
        hoja=config.DIRECTORIO_INDICIOS_SHEET,
        skiprows=config.DIRECTORIO_INDICIOS_SKIPROWS,
        descripcion="directorio de indicios de vida",
    )

    # La clasificación del comprimido se resuelve con su propio mapeo: la lámina se
    # calculó con `clasificacion_des_rnpdno` (la cruda), que NO es `clasificacion_des`.
    cols = resolver_columnas(
        comprimido, config.DIRECTORIO_INDICIOS_COMPRIMIDO_COLUMN_MAPPING,
        descripcion="comprimido (RNPDNO) para el directorio de indicios",
    )
    clas = (comprimido[[cols["fub"], cols["clasificacion_des"]]]
            .rename(columns={cols["fub"]: "fub",
                             cols["clasificacion_des"]: "clasificacion_des"})
            .copy())
    clas["fub"] = clas["fub"].astype(str).str.upper()

    d = directorio.copy()
    d["fub"] = d["fub"].astype(str).str.upper()
    estado = d["estado_de_desaparicion"]
    estado_texto = estado.astype("string").str.strip().str.replace(
        r"\s+", " ", regex=True
    )
    sin_estado_mask = (
        estado.isna()
        | pd.to_numeric(estado_texto, errors="coerce").eq(33).fillna(False)
        | estado_texto.str.casefold().eq("nacido en el extranjero").fillna(False)
    )
    if imputar and sin_estado_mask.any():
        # Sólo se imputa a los LOCALIZADOS sin entidad (los del marcador
        # `sisf`): son los únicos que la lámina excluye de la gráfica. Los
        # todavía desaparecidos sin entidad se quedan en "Sin información",
        # para no mover las barras de los demás estados respecto de la
        # lámina original de las 32.
        fubs_loc = set(clas.loc[clas["clasificacion_des"].isin(
            config.DIRECTORIO_INDICIOS_CLASIF_LOCALIZADO), "fub"])
        objetivo = sin_estado_mask & d["fub"].isin(fubs_loc)
        if objetivo.any():
            imputado = _imputar_estado(d.loc[objetivo, "fub"], comprimido,
                                       cols["fub"], verbose)
            imputado = imputado.reindex(estado.index)
            estado = estado.mask(imputado.notna(), imputado)
            sin_estado_mask = sin_estado_mask & imputado.isna()
    d["estado_de_desaparicion"] = (
        estado.mask(sin_estado_mask, config.DIRECTORIO_INDICIOS_SIN_ESTADO)
        .replace(config.DIRECTORIO_INDICIOS_RENOMBRES)
    )
    d = d.merge(clas, on="fub", how="left")

    es_loc = d["clasificacion_des"].isin(config.DIRECTORIO_INDICIOS_CLASIF_LOCALIZADO)
    sin_estado = int((sin_estado_mask & es_loc).sum())
    # Un FUB que no cruza sigue contando como desaparecido: no hay evidencia de
    # localización, y descartarlo inflaría el porcentaje de formalizados.
    es_des = (d["clasificacion_des"].isin(config.DIRECTORIO_INDICIOS_CLASIF_DESAPARECIDO)
              | d["clasificacion_des"].isna())

    def _por_entidad(mask, nombre):
        return (d.loc[mask]
                .value_counts("estado_de_desaparicion")
                .reset_index(name=nombre))

    tabulado = (
        _por_entidad(es_des, "todavia_desaparecidos")
        .merge(_por_entidad(es_loc, "localizados"),
               on="estado_de_desaparicion", how="outer")
        .fillna({"todavia_desaparecidos": 0, "localizados": 0})
        .astype({"todavia_desaparecidos": int, "localizados": int})
        .sort_values("todavia_desaparecidos", ascending=False)
        .reset_index(drop=True)
    )

    # El conteo nacional se toma ANTES de acotar por entidad: mismo criterio de
    # formalización, pero sobre todo el directorio. Se conserva para el
    # denominador de `pct` y el complemento `resto`.
    nacional = int(es_loc.sum())

    # La lámina de las 32 entidades: el mismo tabulado, sin acotar a la Búsqueda
    # Generalizada. Se toma ANTES de acotarlo a esas entidades y sólo deja fuera
    # lo que no es una entidad federativa ("Nacido en el extranjero"). Las 32 salen
    # del catálogo INEGI de config, con los mismos renombres que el directorio.
    entidades_32 = [config.DIRECTORIO_INDICIOS_RENOMBRES.get(nombre, nombre)
                    for clave, nombre in config.ENTIDADES.items() if clave <= 32]
    fuera_32 = sorted(set(tabulado["estado_de_desaparicion"]) - set(entidades_32))
    tabulado_32 = (tabulado[tabulado["estado_de_desaparicion"].isin(entidades_32)]
                   .reset_index(drop=True))
    total_32 = int(tabulado_32["localizados"].sum())

    # Sólo las entidades que pide la lámina. Las demás salen del conteo a propósito.
    seleccion = config.DIRECTORIO_INDICIOS_ESTADOS
    fuera = sorted(set(tabulado["estado_de_desaparicion"]) - set(seleccion))
    tabulado = (tabulado[tabulado["estado_de_desaparicion"].isin(seleccion)]
                .sort_values("todavia_desaparecidos", ascending=False)
                .reset_index(drop=True))

    total = int(tabulado["localizados"].sum())
    # Las personas del directorio que están en esas entidades, o sea las dos
    # series de la gráfica sumadas. Es el 33,430 que la lámina rotula
    # "Entidades participantes en la Búsqueda Generalizada".
    universo = total + int(tabulado["todavia_desaparecidos"].sum())
    # Denominador del porcentaje: el total de formalizados del directorio.
    # El `pct` responde qué parte cae en las entidades de Búsqueda Generalizada.
    pct = f"{100 * total / nacional:.1f}%" if nacional else "n/d"
    # Los formalizados del resto del país: el complemento de `total` dentro de
    # `nacional`, que es lo que pide el marcador `_v3`.
    resto = nacional - total

    if verbose:
        sin_cruce = int(d["clasificacion_des"].isna().sum())
        print(f"  📇 Directorio de indicios ({config.DIRECTORIO_INDICIOS_FECHA_CORTE}): "
              f"{len(directorio):,} personas")
        print(f"     formalizados como localización : {total:,} "
              f"({pct} del total del país)")
        print(f"     todavía desaparecidos          : "
              f"{int(tabulado['todavia_desaparecidos'].sum()):,}")
        print(f"     entidades en la lámina         : {len(tabulado)} de {len(seleccion)}")
        print(f"     formalizados en todo el país   : {nacional:,}")
        print(f"     formalizados en el resto       : {resto:,}")
        print(f"     formalizados en 32 entidades   : {total_32:,} "
              f"({len(tabulado_32)} de {len(entidades_32)} entidades en la gráfica)")
        if fuera:
            print(f"     ⚠️ fuera del conteo por no estar en "
                  f"DIRECTORIO_INDICIOS_ESTADOS: {', '.join(fuera)}")
        if fuera_32:
            print(f"     ⚠️ fuera de las 32 entidades: {', '.join(fuera_32)}")
        if sin_cruce:
            print(f"     ⚠️ {sin_cruce:,} FUB del directorio no están en el RNPDNO; "
                  f"cuentan como todavía desaparecidos.")

    return tabulado, tabulado_32, {"total": total, "universo": universo,
                                   "universo_nacional": len(directorio),
                                   "pct": pct, "nacional": nacional, "resto": resto,
                                   "total_32": total_32, "sin_estado": sin_estado}
