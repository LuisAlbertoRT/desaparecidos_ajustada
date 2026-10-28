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


def indicios_formalizados(comprimido, verbose: bool = True):
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
        - `total_32` : formalizados en las 32 entidades federativas, o sea
                       `nacional` sin lo que no es una entidad ("Nacido en el
                       extranjero"); alimenta el marcador `_v4`.
        - `sin_estado`: registros localizados sin entidad federativa de
                        desaparición, que se excluyen del desglose por entidad.
    """
    directorio = leer_excel(
        config.DIRECTORIO_INDICIOS_FILE,
        config.DIRECTORIO_INDICIOS_COLUMN_MAPPING,
        hoja=config.DIRECTORIO_INDICIOS_SHEET,
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
    # formalización, pero sobre todo el directorio. Alimenta el marcador `_v2`,
    # que la lámina rotula "Total de país".
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
    # Denominador del porcentaje: el TOTAL DEL PAÍS de formalizados, el mismo
    # conteo del marcador `_v2`. El `pct` responde entonces qué parte de los
    # formalizados del país cae en las entidades de la Búsqueda Generalizada.
    pct = f"{100 * total / nacional:.1f}%" if nacional else "n/d"
    # Los formalizados del resto del país: el complemento de `total` dentro de
    # `nacional`, que es justo lo que pide el marcador `_v3`. Se resta aquí y no
    # en el cuaderno para que las tres cifras de la lámina —la de las entidades,
    # la del país y la del resto— salgan de la misma pasada y no puedan discrepar.
    resto = nacional - total

    if verbose:
        sin_cruce = int(d["clasificacion_des"].isna().sum())
        print(f"  📇 Directorio de indicios ({config.DIRECTORIO_INDICIOS_CORTE}): "
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
                                   "pct": pct, "nacional": nacional, "resto": resto,
                                   "total_32": total_32, "sin_estado": sin_estado}
