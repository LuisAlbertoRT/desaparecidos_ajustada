import pandas as pd
import re
import unidecode

MESES_ES = {"01": "enero", "02": "febrero", "03": "marzo", "04": "abril",
            "05": "mayo", "06": "junio", "07": "julio", "08": "agosto",
            "09": "septiembre", "10": "octubre", "11": "noviembre", "12": "diciembre"}


def formatear_fecha_es(fecha_str, partes: str = "dia_mes_anio"):
    """Convierte 'YYYY-MM-DD' a texto en español, con las partes que se pidan.

    `partes` es la misma cola de tokens que llevan los marcadores de la
    plantilla, así que el nombre del marcador dicta el formato sin traducción
    intermedia:

        dia_mes_anio → "18 de agosto de 2026"   (fha_rn_dia_mes_anio)
        mes_anio     → "agosto de 2026"         (fha_rn_mes_anio)
        dia_mes      → "18 de agosto"
        anio         → "2026"                   (fha_rn_anio)

    Las partes se unen con " de ", que es lo que hace bien las cuatro formas.
    Una entrada que no sea una fecha ISO se devuelve tal cual, como antes.
    """
    if not fecha_str or not isinstance(fecha_str, str):
        return fecha_str
    trozos = fecha_str.split("-")
    if len(trozos) != 3:
        return fecha_str
    anio, mes, dia = trozos

    valores = {"dia": str(int(dia)), "mes": MESES_ES.get(mes, mes), "anio": anio}
    solicitadas = partes.split("_")
    desconocidas = [t for t in solicitadas if t not in valores]
    if desconocidas:
        raise ValueError(
            f"Partes de fecha no reconocidas: {desconocidas}. Usa {sorted(valores)}."
        )
    return " de ".join(valores[t] for t in solicitadas)

def get_id_estado(nombre_estado, entidades_dict):
    """
    Retorna el ID numérico (clave) dado el nombre de la entidad.
    Busca en el diccionario de entidades (ej. config.ENTIDADES: {ID: 'Nombre'}).
    """
    if not nombre_estado: return None
    norm = str(nombre_estado).upper().strip()
    repl = {"Á":"A", "É":"E", "Í":"I", "Ó":"O", "Ú":"U"}
    for a,b in repl.items(): norm = norm.replace(a,b)
    
    # Invertir diccionario para buscar por valor ignorando mayúsculas/acentos
    for k, v in entidades_dict.items():
        v_norm = str(v).upper().strip()
        for a,b in repl.items(): v_norm = v_norm.replace(a,b)
        if v_norm == norm:
            return k
            
    return None

def normalize_header(s):
    """
    Normaliza un string para ser usado como nombre de columna:
    - Minúsculas
    - Sin espacios (reemplazados por _)
    - Sin acentos
    - Sin caracteres especiales
    """
    if not isinstance(s, str):
        return str(s)
    
    s = unidecode.unidecode(s) # Quitar acentos
    s = s.lower().strip()
    s = re.sub(r'[\s\.\-]+', '_', s) # Espacios, puntos, guiones a _
    s = re.sub(r'[^a-z0-9_]', '', s) # Quitar cualquier otro caracter raro
    return s

def standardize_columns(df: pd.DataFrame, mapping_dict: dict, strict=False, verbose=True) -> pd.DataFrame:
    """
    Renombra las columnas del DataFrame basándose en un diccionario de mapeo.
    Busca coincidencias flexibles (normalizando nombres).

    Args:
        df: DataFrame a procesar.
        mapping_dict: Diccionario { 'nombre_objetivo': ['alias1', 'alias2'] }
        strict: Si es True, advierte sobre columnas faltantes (no lanza error para no romper flujo, pero avisa).
        verbose: Imprimir cambios realizados.

    Returns:
        DataFrame con columnas renombradas.
    """
    df = df.copy()
    
    # Mapa de columnas actuales normalizadas -> nombre real
    # Ejemplo: 'fecha_hechos' -> 'Fha. de Hchos.'
    current_cols_norm = {normalize_header(c): c for c in df.columns}
    
    rename_map = {}
    missing_cols = []
    
    for target, aliases in mapping_dict.items():
        # Si la columna ya existe tal cual, pasamos
        if target in df.columns:
            continue
            
        found = False
        # Primero buscamos match exacto en la lista de alias
        # Luego buscamos match normalizado
        
        # Estrategia: Normalizar también los aliases para comparar peras con peras
        for alias in aliases:
            norm_alias = normalize_header(alias)
            
            if norm_alias in current_cols_norm:
                original_col = current_cols_norm[norm_alias]
                rename_map[original_col] = target
                found = True
                break
        
        if not found:
            missing_cols.append(target)

    if rename_map:
        if verbose:
            print(f"  🔄 Estandarizando columnas: Renombrando {len(rename_map)} columnas.")
            for list_orig, list_dest in rename_map.items():
                 print(f"     - '{list_orig}' -> '{list_dest}'")
        df = df.rename(columns=rename_map)
    
    if strict and missing_cols:
        error_msg = f"❌ Error crítico: No se encontraron las siguientes columnas requeridas: {missing_cols}"
        print(error_msg)
        raise ValueError(error_msg)
        
    return df

# ── Series mensuales ─────────────────────────────────────────────────────────
def agrupar_por_mes(df: pd.DataFrame, col_fecha: str, columnas=None,
                    completar_meses: bool = False, nombre_mes: str = "mes",
                    nombre_conteo: str = "registros",
                    desde=None, hasta=None,
                    verbose: bool = True) -> pd.DataFrame:
    """Cuenta registros por mes, opcionalmente abiertos por otras columnas.

    El mes se representa como la FECHA del día primero (`2026-03-01`), no como
    texto ni como `Period`: así la columna sigue siendo `datetime64` y los ejes
    de tiempo de matplotlib la ordenan y la formatean solos. Un `"2026-3"` en
    texto ordenaría "10" antes que "2".

    `columnas` son llaves de agrupación adicionales —`"entidad"`,
    `["entidad", "sexo"]`— que abren una serie por combinación. El resultado
    sale en formato largo (`mes`, *columnas*, `registros`), que es justo lo que
    esperan `1_funciones/lineas.py` y `barras_verticales.py`.

    Las filas cuya fecha no se puede interpretar no tienen mes al que
    pertenecer y quedan fuera; con `verbose=True` se avisa cuántas fueron, para
    que no se pierdan en silencio.

    Con `completar_meses=True` se rellenan con cero los meses sin registros,
    entre el primero y el último observados. Los meses vacíos no existen en el
    `groupby`, y sin rellenarlos una línea de tiempo une los extremos del hueco
    con un tramo recto que aparenta continuidad. Queda apagado por defecto
    porque introduce filas que no estaban en los datos.

    `desde` y `hasta` fijan los extremos de esa rejilla cuando los observados
    no bastan: una rebanada a la que se le acaban los registros antes del final
    del período perdería sus últimos meses del eje —no aparecerían en cero—, y
    dos gráficas del mismo período terminarían en meses distintos. Sólo AMPLÍAN
    la rejilla, nunca la recortan: un registro fuera de [desde, hasta] sigue
    contando en su mes. Exigen `completar_meses=True`.
    """
    if (desde is not None or hasta is not None) and not completar_meses:
        raise ValueError("`desde`/`hasta` sólo aplican con `completar_meses=True`.")

    cols = [columnas] if isinstance(columnas, str) else list(columnas or [])

    faltantes = [c for c in (col_fecha, *cols) if c not in df.columns]
    if faltantes:
        raise KeyError(
            f"El DataFrame no trae {faltantes}. Disponibles: {list(df.columns)}"
        )
    if nombre_mes in cols or nombre_conteo in cols:
        raise ValueError(
            f"'{nombre_mes}'/'{nombre_conteo}' chocan con una columna de "
            f"agrupación; pasa otro `nombre_mes` o `nombre_conteo`."
        )

    fechas = pd.to_datetime(df[col_fecha], errors="coerce", utc=True)
    validas = fechas.notna()
    sin_fecha = int((~validas).sum())

    datos = df.loc[validas, cols].copy()
    # to_period("M").to_timestamp() ancla cada fecha al primero de su mes.
    datos[nombre_mes] = fechas[validas].dt.to_period("M").dt.to_timestamp()

    llaves = [nombre_mes, *cols]
    out = (datos.groupby(llaves, observed=True)   # observed: sin producto
                .size()                            # cartesiano de categóricas
                .reset_index(name=nombre_conteo))

    extremos = [pd.Timestamp(f, tz="UTC").to_period("M").to_timestamp()
                for f in (desde, hasta) if f is not None]
    if not out.empty:
        extremos += [out[nombre_mes].min(), out[nombre_mes].max()]

    if completar_meses and extremos:
        meses = pd.DataFrame({
            nombre_mes: pd.date_range(min(extremos), max(extremos), freq="MS")
        })
        # Una rejilla completa por cada combinación realmente observada: no se
        # inventan combinaciones que nunca ocurrieron, sólo meses que faltaban.
        rejilla = (out[cols].drop_duplicates().merge(meses, how="cross")
                   if cols else meses)
        out = rejilla.merge(out, on=llaves, how="left")
        out[nombre_conteo] = out[nombre_conteo].fillna(0).astype(int)

    out = out[[nombre_mes, *cols, nombre_conteo]].sort_values(llaves)
    out = out.reset_index(drop=True)

    if verbose:
        n_meses = out[nombre_mes].nunique()
        print(f"  📆 {len(df):,} registros → {len(out):,} filas / "
              f"{n_meses} meses" + (f" × {len(cols)} llave(s)" if cols else ""))
        if sin_fecha:
            print(f"     ⚠️ {sin_fecha:,} sin fecha válida en '{col_fecha}', "
                  f"fuera de la serie.")
    return out


# ── Cortes de referencia (25/03/2026 y 01/07/2026) ───────────────────────────
def fubs_corte(marcador: str, verbose: bool = True) -> tuple:
    """`(fubs, filas_sin_fub)` de un marcador de un corte de referencia.

    Cada corte —`input/datos_marzo`, `input/datos_julio`— llega como Excel ya
    rebanado, un archivo por marcador, y no pasa por el pipeline. El archivo y
    la columna del `fub` salen de `config.CORTES_REFERENCIA`: marzo lo trae
    como `fub` y julio como `fub_rnpdno`. Se lee sólo esa columna: los
    archivos traen 27-32 y pesan ~8 MB cada uno.

    El primer elemento son los `fub` distintos y no vacíos. El segundo, cuántas
    filas venían SIN `fub`: no pueden cruzarse contra nada, así que se cuentan
    aparte y alimentan el marcador `_dfub`.

    El `fub` es la llave de persona del RNPDNO, así que una fila sin él no
    pertenece a la base `rn` que el marcador dice medir: en
    `reg_rn_25mar26_des_cisf_sind` las 137 filas sin `fub` son todas
    `origen_categoria_union == "Solo banci, sin intersección"` —registros que no
    existen en el RNPDNO— y quedan fuera del cruce, igual que las deja fuera el
    conteo del pipeline sobre la base `rn`.
    """
    import openpyxl
    import config

    if marcador not in config.CORTES_REFERENCIA:
        raise KeyError(
            f"'{marcador}' no está en config.CORTES_REFERENCIA. "
            f"Disponibles: {sorted(config.CORTES_REFERENCIA)}"
        )
    ruta, col_id = config.CORTES_REFERENCIA[marcador]
    if not ruta.exists():
        raise FileNotFoundError(f"Falta el archivo del corte de referencia: {ruta}")

    wb = openpyxl.load_workbook(ruta, read_only=True)
    try:
        ws = wb.worksheets[0]
        encabezado = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        try:
            i = [normalize_header(c) for c in encabezado].index(normalize_header(col_id))
        except ValueError:
            raise KeyError(
                f"{ruta.name} no trae la columna '{col_id}'. Encabezado: {encabezado}"
            )
        # iter_rows acotado a una columna devuelve tuplas de longitud 1.
        ids, sin_fub = set(), 0
        for fila in ws.iter_rows(min_row=2, min_col=i + 1, max_col=i + 1,
                                 values_only=True):
            if fila[0] in (None, ""):
                sin_fub += 1
            else:
                ids.add(str(fila[0]).strip())
    finally:
        wb.close()

    if verbose:
        aviso = f"  (+{sin_fub:,} filas sin fub)" if sin_fub else ""
        print(f"  📄 {marcador}: {len(ids):,} registros ({ruta.name}){aviso}")
    return ids, sin_fub


def contar_corte(marcador: str, verbose: bool = True) -> int:
    """Registros de un marcador de un corte de referencia. Ver `fubs_corte`."""
    return len(fubs_corte(marcador, verbose=verbose)[0])


def diferencias_vs_corte(vars_ppt: dict, marcadores: dict,
                         porcentajes: bool = True,
                         verbose: bool = True) -> dict:
    """Marcadores `<actual>-<corte>` = crecimiento desde un corte de referencia.

    `marcadores` mapea el nombre del indicador ya calculado por el pipeline al
    nombre del marcador del corte, p. ej.
    `{"reg_rn_01ene06-max_des_sisf": "reg_rn_25mar26_des_sisf"}`.
    La clave que se emite es la concatenación con guion que usa la plantilla:
    `reg_rn_01ene06-max_des_sisf-reg_rn_25mar26_des_sisf`. El corte puede ser
    de cualquier fecha de `config.CORTES_REFERENCIA`: con
    `"reg_rn_01jul26_des_sisf"` la clave es `...-reg_rn_01jul26_des_sisf`.

    Con `porcentajes=True` emite además `pct_<misma clave>`: la diferencia
    medida contra el corte, es decir el crecimiento porcentual.
    """
    salida = {}
    for actual, corte in marcadores.items():
        if actual not in vars_ppt:
            raise KeyError(
                f"'{actual}' no está en vars_ppt; agrégalo a CONTEOS antes de "
                f"restarle el corte {corte}."
            )
        n_actual = int(vars_ppt[actual])
        n_corte = contar_corte(corte, verbose=verbose)
        clave = f"{actual}-{corte}"
        salida[clave] = n_actual - n_corte
        salida[corte] = n_corte
        if porcentajes:
            salida[f"pct_{clave}"] = (
                f"{100 * (n_actual - n_corte) / n_corte:.1f}%" if n_corte else "n/d"
            )
        if verbose:
            print(f"  ➖ {clave} = {n_actual:,} − {n_corte:,} = {salida[clave]:,}")
    return salida


def deltas_vs_corte(universo, marcadores: dict, sufijo: str = "",
                    verbose: bool = True) -> dict:
    """Altas y bajas de un indicador respecto a un corte de referencia.

    A diferencia de `diferencias_vs_corte`, que resta dos totales, aquí se
    comparan los CONJUNTOS de `fub`. La resta de totales sólo da el saldo
    neto; el cruce por identificador separa las dos corrientes que lo componen,
    que suelen ser mucho mayores que su diferencia:

        ddes = en el indicador de hoy y NO en el corte  → altas
        dloc = en el corte y NO en el indicador de hoy  → bajas
        dfub = sin `fub` en cualquiera de los dos lados → sin cruzar

    Un registro sale del indicador porque la persona fue localizada (de ahí
    `dloc`) o porque dejó de cumplir el subfiltro —por ejemplo perdió el
    registro administrativo activo en PUI—, así que `dloc` es una cota superior
    de las localizaciones, no su conteo exacto.

    Por construcción `ddes − dloc` es la diferencia de totales, de modo que
    cuadra con `diferencias_vs_corte`. Los `_dfub` quedan fuera de esa
    identidad: sin llave no hay cruce posible, y tampoco entran en los totales
    del pipeline, que sólo cuenta registros de la base `rn`. La clave `_dfub`
    sólo se emite cuando hay alguno.

    `marcadores` mapea cada `Slice` al nombre del marcador del corte:
    `{Slice("rn", "01ene06-max", estatus="des", subfiltro="sisf"):
      "reg_rn_25mar26_des_sisf"}`.

    El nombre del marcador no dice contra qué corte se cruzó: la plantilla lo
    distingue con `sufijo`, que se pega al final de las tres claves. El corte de
    marzo va sin sufijo (`_ddes`) y el de julio con `"_v2"` (`_ddes_v2`).
    """
    salida = {}
    for s, corte in marcadores.items():
        serie = universo.slice(s)["fub_rnpdno"]
        actuales = {f for f in serie.dropna().astype(str).str.strip() if f}
        sin_fub_hoy = len(serie) - len(actuales)
        previos, sin_fub_corte = fubs_corte(corte, verbose=verbose)
        altas, bajas = actuales - previos, previos - actuales
        salida[f"{s.nombre}_ddes{sufijo}"] = len(altas)
        salida[f"{s.nombre}_dloc{sufijo}"] = len(bajas)

        # Un registro sin `fub` no tiene con qué cruzarse: no puede caer en
        # altas ni en bajas. Se cuenta aparte para que no desaparezca en
        # silencio, y sólo se emite la clave cuando de verdad hay alguno,
        # que es como aparece en la plantilla (sólo `cisf_sind` de marzo los trae).
        sin_fub = sin_fub_hoy + sin_fub_corte
        if sin_fub:
            salida[f"{s.nombre}_dfub{sufijo}"] = sin_fub

        if verbose:
            print(f"  ⇄ {s.nombre} vs {corte}: "
                  f"+{len(altas):,} altas (_ddes{sufijo}) / −{len(bajas):,} bajas "
                  f"(_dloc{sufijo}) → neto {len(altas) - len(bajas):+,}")
            if sin_fub:
                print(f"     ⚠️ {sin_fub:,} registros sin fub, fuera del cruce "
                      f"(_dfub{sufijo}): {sin_fub_hoy:,} de hoy + {sin_fub_corte:,} del corte.")
    return salida


# ─────────────────────────────────────────────────────────────────────────────
# RNIP y MJ (MJ + RIPS) · última lámina del reporte diario
# ─────────────────────────────────────────────────────────────────────────────
# Denominador de cada porcentaje de la lámina. Es la regla del padre de
# `Slice.padre` —cada indicador contra su nivel inmediato superior—, escrita a
# mano porque `mr` no es una rebanada del universo y no pasa por `Slice`:
#     des  y  loc   se reparten el total del archivo   (suman 100%)
#     cvid y  svid  se reparten los localizados        (suman 100%)
MJ_RIPS_DENOMINADOR = {
    "reg_mr_min-max_des":      "reg_mr_min-max",
    "reg_mr_min-max_loc":      "reg_mr_min-max",
    "reg_mr_min-max_loc_cvid": "reg_mr_min-max_loc",
    "reg_mr_min-max_loc_svid": "reg_mr_min-max_loc",
}


def cruzar_mj_rips(rn, verbose: bool = True):
    """Estatus vigente en el RNPDNO de las personas con detención penitenciaria.

    El archivo de MJ y RIPS (`config.MJ_RIPS_FILE`) es una foto congelada de
    quiénes aparecieron en un Mandamiento Judicial o en el registro
    penitenciario. Cruzarlo por `fub` contra el RNPDNO vigente responde:
    **de esas personas, ¿cuántas siguen desaparecidas y cuántas ya están
    localizadas, con vida o sin ella?**

    No es una rebanada del universo y por eso no pasa por `Slice`, igual que
    `indicios_formalizados`: su población sale de un archivo externo, no del
    RNPDNO ni de BANCI, y su "período" es la fecha del corte, no un rango de
    fechas de hechos. Los conteos se inyectan como `extra=` en
    `Universo.indicadores`. El token `min-max` del nombre de los marcadores no
    rebana nada: el archivo se toma completo.

    Las dos hojas se concatenan SIN deduplicar. Un `fub` puede venir en las dos
    —está en MJ y además en RIPS— y ahí son dos registros, que es lo que cuenta
    la lámina ("Total registros de RNIP y MJ"). La columna `tipo` dice de cuál
    hoja vino cada uno.

    Parameters
    ----------
    rn : DataFrame
        Universo RNPDNO derivado (`Universo.rn`). Debe traer las columnas de
        `config.MJ_RIPS_RNPDNO_COLUMN_MAPPING`: `fub`, `estatus_loc` y las
        banderas `is_cvid` / `is_svid`.
    verbose : bool
        Imprime el desglose y avisa de los FUB que no cruzan.

    Returns
    -------
    (subconjuntos, conteos)
        `subconjuntos` es un dict {nombre de marcador: DataFrame}, con el
        universo completo y sus cuatro subconjuntos:

            reg_mr_min-max            todos los registros del archivo
            reg_mr_min-max_des        los que hoy siguen desaparecidos
            reg_mr_min-max_loc        los que hoy están localizados
            reg_mr_min-max_loc_cvid   de esos localizados, con vida
            reg_mr_min-max_loc_svid   de esos localizados, sin vida

        `des + loc = total` y `cvid + svid = loc`, así que las dos parejas son
        particiones y sus porcentajes suman 100%.

        `conteos` trae esos cinco conteos, sus cuatro `pct_` (contra el
        denominador de `MJ_RIPS_DENOMINADOR`) y las variantes de
        `fha_mr_*` con la fecha de corte declarada en config. Va directo al
        `extra=` de `Universo.indicadores`.
    """
    import config
    from src.validacion import leer_excel, resolver_columnas

    # Una hoja por fuente, con el mismo mapeo: las dos traen esquemas distintos
    # (MJ 26 columnas, RIPS 18) pero comparten las siete que se usan.
    hojas = []
    for tipo, hoja in config.MJ_RIPS_SHEETS.items():
        d = leer_excel(
            config.MJ_RIPS_FILE, config.MJ_RIPS_COLUMN_MAPPING, hoja=hoja,
            descripcion=f"MJ y RIPS · hoja '{hoja}'",
        )
        d["tipo"] = tipo
        hojas.append(d)
    mr = pd.concat(hojas, ignore_index=True, sort=False)
    mr["fub"] = mr["fub"].astype(str).str.strip().str.upper()

    # Del universo sólo se toma el estatus: la lámina no pregunta nada más del
    # RNPDNO, y traer el frame completo duplicaría 50 columnas por registro.
    cols = resolver_columnas(
        rn, config.MJ_RIPS_RNPDNO_COLUMN_MAPPING,
        descripcion="universo RNPDNO para el cruce con MJ y RIPS",
    )
    est = rn[[cols[k] for k in config.MJ_RIPS_RNPDNO_COLUMN_MAPPING]].copy()
    est.columns = list(config.MJ_RIPS_RNPDNO_COLUMN_MAPPING)
    est["fub"] = est["fub"].astype(str).str.strip().str.upper()
    # El RNPDNO derivado trae un renglón por FUB. Si eso dejara de cumplirse, el
    # merge duplicaría registros de `mr` y el total de la lámina ya no sería el
    # del archivo, así que se garantiza aquí en vez de confiar en la fuente.
    est = est.drop_duplicates("fub")

    mr = mr.merge(est, on="fub", how="left")

    # Un FUB que no está en el RNPDNO no tiene evidencia de localización: cuenta
    # como desaparecido. Descartarlo inflaría el porcentaje de localizados, y
    # ése es justo el número que lee la lámina.
    mr["in_rn"] = mr["estatus_loc"].notna()
    mr["estatus_loc"] = mr["estatus_loc"].fillna("des")
    for bandera in ("is_cvid", "is_svid"):
        mr[bandera] = mr[bandera].fillna(False).astype(bool)

    es_loc = mr["estatus_loc"].eq("loc").to_numpy()
    subconjuntos = {
        "reg_mr_min-max":          mr,
        "reg_mr_min-max_des":      mr[~es_loc],
        "reg_mr_min-max_loc":      mr[es_loc],
        "reg_mr_min-max_loc_cvid": mr[es_loc & mr["is_cvid"].to_numpy()],
        "reg_mr_min-max_loc_svid": mr[es_loc & mr["is_svid"].to_numpy()],
    }

    conteos = {nombre: len(df) for nombre, df in subconjuntos.items()}
    for nombre, denominador in MJ_RIPS_DENOMINADOR.items():
        den = conteos[denominador]
        conteos[f"pct_{nombre}"] = (
            f"{100 * conteos[nombre] / den:.1f}%" if den else "n/d"
        )
    # Mismas variantes que emite `Universo.indicadores` para `rn` y `ba`: la
    # cola del marcador ES el formato, así que emitirlas todas sale gratis.
    for partes in ("dia_mes_anio", "mes_anio", "anio"):
        conteos[f"fha_mr_{partes}"] = formatear_fecha_es(
            config.MJ_RIPS_FECHA_CORTE, partes)

    if verbose:
        total = conteos["reg_mr_min-max"]
        print(f"  🔗 MJ y RIPS (corte {config.MJ_RIPS_FECHA_CORTE}): "
              f"{total:,} registros")
        print(f"     por hoja                       : "
              + ", ".join(f"{t}={n:,}" for t, n in mr['tipo'].value_counts().items()))
        den_texto = {"reg_mr_min-max": "del total",
                     "reg_mr_min-max_loc": "de los localizados"}
        for nombre, etiqueta in (("reg_mr_min-max_des",      "todavía desaparecidos"),
                                 ("reg_mr_min-max_loc",      "localizados"),
                                 ("reg_mr_min-max_loc_cvid", "  · con vida"),
                                 ("reg_mr_min-max_loc_svid", "  · sin vida")):
            print(f"     {etiqueta:<31}: {conteos[nombre]:>6,} "
                  f"({conteos[f'pct_{nombre}']} "
                  f"{den_texto[MJ_RIPS_DENOMINADOR[nombre]]})")
        repetidos = int(mr["fub"].duplicated().sum())
        if repetidos:
            print(f"     ℹ️ {repetidos:,} FUB vienen en las dos hojas; cuentan "
                  f"como dos registros, igual que en el archivo.")
        sin_cruce = int((~mr["in_rn"]).sum())
        if sin_cruce:
            print(f"     ⚠️ {sin_cruce:,} FUB de MJ y RIPS no están en el RNPDNO; "
                  f"cuentan como todavía desaparecidos.")

    return subconjuntos, conteos


def remove_timezone_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Remove timezone from datetime columns for Excel compatibility.
    
    Excel does not support datetimes with timezones. This function converts
    all tz-aware datetime columns to tz-naive in a copy of the dataframe.
    
    Args:
        df: DataFrame that may contain tz-aware datetime columns
        
    Returns:
        DataFrame with all timezone information removed from datetime columns
    """
    df_out = df.copy()
    for col in df_out.columns:
        if hasattr(df_out[col], 'dt') and hasattr(df_out[col].dt, 'tz'):
            if df_out[col].dt.tz is not None:
                df_out[col] = df_out[col].dt.tz_localize(None)
    return df_out
