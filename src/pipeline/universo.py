"""Orquestador del pipeline con caché de dos niveles.

    Universo.construir(cfg)
        ├── nivel 1 · matching   (clave_matching)  ~minutos
        └── nivel 2 · derivadas  (clave_universo)  ~segundos

Cada nivel se salta si su caché sigue valiendo, y eso exige dos cosas:

1. La LLAVE coincide. `Settings.clave_matching` / `clave_universo` resumen todo lo
   que puede mover un resultado: los campos del perfil, config.py tal como lo ve
   esta corrida, el código de la capa y la firma de los insumos (ver
   `src/pipeline/huella.py`). Cambiar cualquiera da otra llave, y el caché viejo
   simplemente no se encuentra.
2. Ningún archivo que se leyó al escribirlo cambió desde entonces. Se registran
   al construir (`huella.registrar_lecturas`) y se revisan al leer.

Como la llave no depende del período, el estatus, el subfiltro ni la entidad,
cambiar cualquiera de esos cuatro es un acierto de caché: el costo baja de
minutos a la lectura de unos Parquet.

Consumo desde un notebook de PPT:

    cfg = Settings.desde_perfil("reporte_diario")
    u   = Universo.construir(cfg)
    df  = u.slice(Slice("rn-si-ba", "01oct24-max", estatus="des"))
    n   = u.contar(Slice("rn", "01oct24-max"))     # sin materializar nada
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Optional

import numpy as np
import pandas as pd

import config
from src import utils
from src.pipeline import huella
from src.settings import Settings
from src.slices import BASES, Slice

if TYPE_CHECKING:
    from src.pipeline.motores import ResultadoMatching


@dataclass
class Universo:
    """RNPDNO y BANCI derivados, listos para rebanar. Nacional, siempre."""

    cfg: Settings
    rn: pd.DataFrame
    ba: pd.DataFrame
    meta: dict = field(default_factory=dict)
    auditoria: Optional[pd.DataFrame] = None
    # La salida de la capa A. La exportación de llaves y las bases del Secretariado
    # la leen de aquí: viene de la misma corrida, o del mismo caché, que el universo.
    matching: Optional["ResultadoMatching"] = field(default=None, repr=False)
    _cache_periodos: dict = field(default_factory=dict, repr=False)

    # ── Construcción ─────────────────────────────────────────────────────────
    @classmethod
    def construir(cls, cfg: Settings, forzar: bool = False,
                  forzar_matching: bool = False, verbose: bool = True) -> "Universo":
        """El universo de `cfg`: del caché si sigue valiendo, si no, desde los insumos.

        `forzar` o `forzar_matching` recalculan todo aunque el caché valga.
        """
        # Las llaves se calculan una sola vez: si un insumo cambiara a media
        # corrida, la carpeta y `meta` no deben quedar con llaves distintas.
        clave_m, clave_u = cfg.clave_matching, cfg.clave_universo
        dir_match = cfg.cache_dir / "matching" / clave_m
        dir_uni = cfg.cache_dir / "universo" / clave_u

        usar_cache = not (forzar or forzar_matching)
        match_ok = usar_cache and _vigente(dir_match, ARCHIVOS_MATCHING, "matching", verbose)
        if match_ok and _vigente(dir_uni, ARCHIVOS_UNIVERSO, "universo", verbose):
            if verbose:
                print(f"⚡ Universo en caché ({clave_u}) → lectura directa.")
            return cls._leer(cfg, dir_uni, dir_match, verbose)

        # ── Nivel 1 · matching ──────────────────────────────────────────────
        from src.pipeline.carga import cargar_fuentes
        from src.pipeline.motores import ejecutar_matching
        from src.pipeline.derivadas import derivar_rnpdno, derivar_banci

        # Lo que se lea aquí queda anotado con su firma: es lo que se revisa al
        # volver a leer el caché. La carpeta del caché no cuenta como insumo.
        with huella.registrar_lecturas(excluir=[cfg.cache_dir]) as leidos:
            fuentes = cargar_fuentes(cfg, verbose=verbose)
            if match_ok:
                if verbose:
                    print(f"⚡ Matching en caché ({clave_m}) → se omiten los 3 motores.")
                res, deps_match = _leer_matching(dir_match)
            else:
                if verbose:
                    print(f"🔧 Ejecutando matching ({clave_m})...")
                res = ejecutar_matching(cfg, fuentes, verbose=verbose)
                deps_match = dict(leidos)
                _escribir_cache(dir_match, "matching", clave_m, deps_match,
                                lambda d: _escribir_matching(d, res, cfg), verbose)

            # ── Nivel 2 · derivadas ─────────────────────────────────────────
            if verbose:
                print("\n🔧 Derivando banderas y curando columnas...")
            rn = derivar_rnpdno(fuentes.rn, res.fubs_matcheados, res.mapa_tipo_match, cfg, verbose)
            ba = derivar_banci(res.banci, rn, cfg, verbose)
            if cfg.propagar_delito_banci:
                from src.pipeline.derivadas import propagar_delito_desde_banci
                rn = propagar_delito_desde_banci(rn, ba, verbose)

        meta = {
            "perfil": cfg.perfil,
            "clave_matching": clave_m,
            "clave_universo": clave_u,
            "generado": datetime.now().isoformat(timespec="seconds"),
            "n_rn": len(rn),
            "n_ba": len(ba),
            "n_fubs_matcheados": len(res.fubs_matcheados),
            "fecha_corte_rnpdno": _max_fecha(fuentes.rn, "fecha_consulta_derivada_rnpdno"),
            "fecha_corte_banci": _max_fecha(ba, "fha_de_hchos_derivada_banci"),
        }
        u = cls(cfg=cfg, rn=rn, ba=ba, meta=meta, auditoria=res.auditoria, matching=res)
        _escribir_cache(dir_uni, "universo", clave_u, {**deps_match, **leidos},
                        u._escribir, verbose)
        return u

    # ── Rebanado ─────────────────────────────────────────────────────────────
    def _frame_y_mascara(self, s: Slice) -> tuple[pd.DataFrame, np.ndarray]:
        """Resuelve una rebanada como (frame base, máscara booleana).

        Nunca copia: las seis bases del catálogo son máscaras sobre `rn` y `ba`,
        no seis DataFrames materializados como en la versión anterior.
        """
        nombre_frame, pertenencia = BASES[s.base]
        df = self.rn if nombre_frame == "rn" else self.ba

        mask = self._mascara_periodo(nombre_frame, s.periodo).copy()

        if pertenencia is not None:
            col, valor = pertenencia
            mask &= df[col].to_numpy() if valor else ~df[col].to_numpy()

        if s.estatus != "all":
            # Ruta rápida de categóricas: compara códigos, no cadenas.
            mask &= (df[self.columna(s, "estatus_loc")] == s.estatus).to_numpy()

        if s.subfiltro != "all":
            # Un subfiltro puede combinar varias banderas: "sfval_ccvac" exige ambas.
            for token in s.subfiltro.split("_"):
                mask &= self._bandera(nombre_frame, df, token, s)

        # La entidad se aplica AQUÍ, no antes del matching.
        if s.estado is not None:
            mask &= (df[self.columna(s, "cve_ent")] == s.estado).fillna(False).to_numpy()

        return df, mask

    @staticmethod
    def _bandera(nombre_frame: str, df: pd.DataFrame, token: str, s: Slice) -> np.ndarray:
        """Valores de la bandera `token` sobre `df`.

        Se resuelve, en orden: constante de la base (CONSTANTES), columna del ETL
        (BANDERAS_ETL) o bandera guardada `is_<token>_derivada_<fuentes>`. Las que
        son la negación exacta de otra no se guardan: se niega la base (NEGACIONES).
        """
        from src.pipeline.derivadas import BANDERAS_ETL, CONSTANTES, NEGACIONES

        base = NEGACIONES.get(token, token)
        if base in CONSTANTES[nombre_frame]:
            valores = np.full(len(df), CONSTANTES[nombre_frame][base], dtype=bool)
        else:
            try:
                valores = df[Universo._col_bandera(nombre_frame, df, base)].to_numpy()
            except KeyError:
                guardadas = {c[3:].split("_derivada_")[0] for c in df.columns if c.startswith("is_")}
                guardadas |= set(BANDERAS_ETL[nombre_frame]) | set(CONSTANTES[nombre_frame])
                disponibles = guardadas | {n for n, b in NEGACIONES.items() if b in guardadas}
                raise KeyError(
                    f"Subfiltro '{token}' (de '{s.subfiltro}') no existe en la base "
                    f"'{s.base}'. Disponibles: {sorted(disponibles)}"
                ) from None
        return ~valores if token in NEGACIONES else valores

    @staticmethod
    def _col_bandera(nombre_frame: str, df: pd.DataFrame, token: str) -> str:
        from src.pipeline.derivadas import BANDERAS_ETL, columna_bandera

        col = BANDERAS_ETL[nombre_frame].get(token)
        if col is not None:
            if col not in df.columns:
                raise KeyError(col)
            return col
        return columna_bandera(df, token)

    @staticmethod
    def _frame(s) -> str:
        return BASES[s.base][0] if isinstance(s, Slice) else s

    def columna(self, s, dimension: str) -> str:
        """Nombre de la columna de una dimensión (`fecha`, `cve_ent`, `entidad`,
        `estatus_loc`) en la base de la rebanada `s` (o en `"rn"` / `"ba"`)."""
        from src.pipeline.derivadas import columna_dimension
        return columna_dimension(self._frame(s), dimension)

    def columna_bandera(self, s, token: str) -> str:
        """Nombre de la columna guardada de la bandera `token` en la base de `s`."""
        frame = self._frame(s)
        return self._col_bandera(frame, self.rn if frame == "rn" else self.ba, token)

    def rango_fechas(self, s: Slice) -> tuple[pd.Timestamp, pd.Timestamp]:
        """Primer y último día que cubre el período de `s`, ambos incluidos.

        Es el eje de tiempo de la rebanada, no el de sus registros: a una
        rebanada se le pueden acabar los registros antes del final del período
        y su eje debe llegar igual hasta ahí. Por eso un extremo abierto
        (`min`/`max`) se resuelve con la fecha extrema de la BASE completa y no
        de la rebanada, y todas las rebanadas de una base comparten el eje.

        No se usa `fecha_corte_*` como final: la del RNPDNO es la fecha de
        consulta, y una consulta del día primero abriría un mes sin hechos
        registrados todavía. Un período cerrado se recorta igual a los datos,
        para no pintar meses que la base aún no alcanza.

        `PERIODOS_TIEMPO` usa [inicio, fin): el último día es `fin` − 1.
        """
        frame = self._frame(s)
        ini, fin = self.cfg.rango_periodo(s.periodo)
        fechas = (self.rn if frame == "rn" else self.ba)[self.columna(frame, "fecha")]
        f_min, f_max = fechas.min(), fechas.max()
        desde = f_min if ini is None else max(pd.Timestamp(ini, tz="UTC"), f_min)
        hasta = f_max if fin is None else min(pd.Timestamp(fin, tz="UTC") - pd.Timedelta(days=1), f_max)
        return desde, hasta

    def _mascara_periodo(self, nombre_frame: str, periodo: str) -> np.ndarray:
        """Máscara de fechas, memorizada por (frame, período).

        Las mismas ventanas se repiden decenas de veces —33 entidades sobre el
        mismo período, por ejemplo— y recalcular la comparación sobre 400k filas
        cada vez domina el costo del rebanado.
        """
        llave = (nombre_frame, periodo)
        cacheada = self._cache_periodos.get(llave)
        if cacheada is not None:
            return cacheada

        df = self.rn if nombre_frame == "rn" else self.ba
        ini, fin = self.cfg.rango_periodo(periodo)
        fecha = df[self.columna(nombre_frame, "fecha")]
        mask = np.ones(len(df), dtype=bool)
        if ini is not None or fin is not None:
            nulas = fecha.isna().to_numpy()
            if ini is not None:
                mask &= (fecha >= pd.to_datetime(ini)).to_numpy() | nulas
            if fin is not None:
                mask &= (fecha < pd.to_datetime(fin)).to_numpy() | nulas
        self._cache_periodos[llave] = mask
        return mask

    def contar(self, s: Slice) -> int:
        """Cuenta sin materializar el DataFrame."""
        _, mask = self._frame_y_mascara(s)
        return int(mask.sum())

    def porcentaje(self, s: Slice, denominador: Optional[Slice] = None,
                   decimales: int = 1, como_texto: bool = True):
        """Porcentaje de una rebanada contra su denominador.

        Por defecto el denominador es `Slice.padre` (la misma rebanada sin su
        último filtro). Pásalo explícito cuando esa regla no aplique: por
        ejemplo `reg_rn-si-ba_01oct24-max_des` contra su padre da 100% —el
        matching sólo alcanza desaparecidos del sexenio—, y lo informativo es
        medirlo contra `reg_rn_01oct24-max_des`.

        Devuelve "33.8%" por defecto, o el número si `como_texto=False`.
        """
        num = self.contar(s)
        den = self.contar(denominador if denominador is not None else s.padre)
        if den == 0:
            return "n/d" if como_texto else float("nan")
        valor = round(100 * num / den, decimales)
        return f"{valor:.{decimales}f}%" if como_texto else valor

    def slice(self, s: Slice, materializar: bool = False) -> pd.DataFrame:
        """Devuelve la rebanada. `materializar=True` la escribe también a Parquet."""
        df, mask = self._frame_y_mascara(s)
        out = df[mask]
        if materializar:
            self.cfg.resultados_dir.mkdir(parents=True, exist_ok=True)
            destino = self.cfg.resultados_dir / f"{s.nombre}.parquet"
            out.to_parquet(destino, index=False, engine="pyarrow")
            print(f"  💾 {s.nombre}: {len(out):,} registros → {destino.name}")
        return out

    def dataframes(self, slices: Iterable[Slice], materializar: bool = False) -> dict[str, pd.DataFrame]:
        return {s.nombre: self.slice(s, materializar) for s in slices}

    def indicadores(self, slices: Iterable[Slice],
                    porcentajes: Optional[Iterable] = None,
                    extra: Optional[dict] = None) -> dict:
        """Conteos + porcentajes + contexto, listos para `PPTReportBuilder`.

        `porcentajes` emite una clave `pct_<nombre>` por rebanada, calculada
        contra su denominador (`Slice.padre`).
        """
        vars_ppt = {s.nombre: self.contar(s) for s in slices}
        for item in (porcentajes or []):
            # Acepta un Slice (denominador = su padre) o (Slice, denominador).
            s, den = item if isinstance(item, tuple) else (item, None)
            vars_ppt[f"pct_{s.nombre}"] = self.porcentaje(s, den)
        vars_ppt["entidad_texto"] = (
            config.ENTIDADES.get(self.cfg.estado, "Nacional") if self.cfg.estado else "Nacional"
        )
        # Marcadores de fecha `fha_<base>_<partes>`: la cola del nombre ES el
        # formato, así que agregar una variante nueva de la plantilla es sumar
        # una línea aquí. Las claves de `self.meta` siguen con el nombre
        # interno; lo que se renombró es lo que ve la plantilla.
        f_rn = self.meta.get("fecha_corte_rnpdno")
        f_ba = self.meta.get("fecha_corte_banci")
        for base, fecha in (("rn", f_rn), ("ba", f_ba)):
            for partes in ("dia_mes_anio", "mes_anio", "anio"):
                vars_ppt[f"fha_{base}_{partes}"] = (
                    utils.formatear_fecha_es(fecha, partes) if fecha else "Sin Fecha"
                )

        # `hoy` no sale de los datos sino del reloj: es la fecha en que se corre
        # el cuaderno, y por eso se calcula aquí y no en `meta`, que se fija al
        # construir el universo: un kernel abierto de un día para otro la
        # arrastraría. Se emiten las mismas variantes que las fechas de corte:
        # reporte_diario.pptx pide `fha_hoy_dia_mes_anio` y reporte_estados.pptx
        # las dos, así que emitirlas todas sale gratis y evita el marcador huérfano.
        f_hoy = datetime.now().strftime("%Y-%m-%d")
        for partes in ("dia_mes_anio", "dia_mes", "mes_anio", "anio"):
            vars_ppt[f"fha_hoy_{partes}"] = utils.formatear_fecha_es(f_hoy, partes)
        if extra:
            vars_ppt.update(extra)
        return vars_ppt

    def exportar_indicadores(self, slices: Iterable[Slice],
                             porcentajes: Optional[Iterable] = None,
                             extra: Optional[dict] = None,
                             destino: Optional[Path] = None) -> pd.DataFrame:
        vars_ppt = self.indicadores(slices, porcentajes, extra)
        df = pd.DataFrame([{"Variable": k, "Valor": v} for k, v in vars_ppt.items()])
        destino = destino or config.INDICADORES_DESAPARECIDOS_FILE
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(destino, index=False, encoding="utf-8-sig")
        print(f"📊 {len(df)} indicadores → {destino}")
        return df

    def resumen(self) -> pd.DataFrame:
        """Panorama rápido del universo cargado."""
        filas = []
        for nombre in BASES:
            s = Slice(nombre, "min-max")
            filas.append({"base": nombre, "registros": self.contar(s)})
        return pd.DataFrame(filas)


    # ── Persistencia ─────────────────────────────────────────────────────────
    def _escribir(self, destino: Path) -> None:
        self.rn.to_parquet(destino / "rn.parquet", index=False, engine="pyarrow")
        self.ba.to_parquet(destino / "ba.parquet", index=False, engine="pyarrow")
        if self.auditoria is not None:
            self.auditoria.to_csv(destino / "auditoria.csv", index=False)
        (destino / "meta.json").write_text(json.dumps(self.meta, indent=2, ensure_ascii=False))

    @classmethod
    def _leer(cls, cfg: Settings, dir_uni: Path, dir_match: Path, verbose: bool) -> "Universo":
        rn = pd.read_parquet(dir_uni / "rn.parquet")
        ba = pd.read_parquet(dir_uni / "ba.parquet")
        meta = json.loads((dir_uni / "meta.json").read_text())
        aud = pd.read_csv(dir_uni / "auditoria.csv") if (dir_uni / "auditoria.csv").exists() else None
        res, _ = _leer_matching(dir_match)
        if verbose:
            print(f"   RNPDNO: {len(rn):,}  |  BANCI: {len(ba):,}  "
                  f"(generado {meta.get('generado', '?')})")
        return cls(cfg=cfg, rn=rn, ba=ba, meta=meta, auditoria=aud, matching=res)


# ─────────────────────────────────────────────────────────────────────────────
# Caché en disco
# ─────────────────────────────────────────────────────────────────────────────
# Lo que deja cada nivel en `cache/<nivel>/<clave>/`, además de `huella.json`.
ARCHIVOS_MATCHING = ("banci.parquet", "match.json", "verif_fecha.parquet",
                     "candidatos_revision.parquet")
ARCHIVOS_UNIVERSO = ("rn.parquet", "ba.parquet", "meta.json")


def _vigente(d: Path, archivos: tuple[str, ...], nivel: str, verbose: bool) -> bool:
    """¿El caché de esta llave está completo y sus insumos siguen iguales?"""
    if not all((d / a).exists() for a in (*archivos, "huella.json")):
        return False
    cambiados = huella.archivos_cambiados(
        json.loads((d / "huella.json").read_text(encoding="utf-8"))["dependencias"])
    if cambiados and verbose:
        print(f"♻️ Caché de {nivel} descartado: cambió "
              + ", ".join(Path(c).name for c in cambiados[:5])
              + (f" y {len(cambiados) - 5} más" if len(cambiados) > 5 else ""))
    return not cambiados


def _escribir_cache(destino: Path, nivel: str, clave: str, dependencias: dict,
                    escribir: Callable[[Path], None], verbose: bool) -> None:
    """Escribe un nivel en una carpeta temporal y la renombra al final.

    Una corrida interrumpida deja, a lo sumo, la carpeta temporal: nunca un caché
    a medias con la llave buena. Tampoco se escribe si el código de la capa
    cambió después de arrancar este kernel (`huella.editados_en_sesion`).
    """
    editados = huella.editados_en_sesion(nivel)
    if editados:
        if verbose:
            print(f"⚠️ No se guardó el caché de {nivel}: {', '.join(editados)} cambió después "
                  "de abrir este kernel, que puede estar corriendo la versión anterior. "
                  "Reinicia el kernel para que el resultado se guarde.")
        return
    tmp = destino.with_name(f"{destino.name}.tmp-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    escribir(tmp)
    (tmp / "huella.json").write_text(json.dumps({
        "clave": clave,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "dependencias": dependencias,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(destino, ignore_errors=True)
    tmp.rename(destino)
    if verbose:
        print(f"💾 Caché de {nivel} guardado en {destino}")


def _escribir_matching(destino: Path, res, cfg: Settings) -> None:
    res.banci.to_parquet(destino / "banci.parquet", index=False, engine="pyarrow")
    res.verif_fecha.to_parquet(destino / "verif_fecha.parquet", index=False, engine="pyarrow")
    res.candidatos.to_parquet(destino / "candidatos_revision.parquet", index=False, engine="pyarrow")
    (destino / "match.json").write_text(json.dumps({
        "fubs_matcheados": sorted(res.fubs_matcheados),
        "mapa_tipo_match": {str(k): v for k, v in res.mapa_tipo_match.items()},
        "perfil": cfg.perfil,
        "generado": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False))
    res.auditoria.to_csv(destino / "auditoria.csv", index=False)


def _leer_matching(origen: Path):
    """La capa A guardada y los archivos de los que dependía."""
    from src.pipeline.motores import ResultadoMatching
    datos = json.loads((origen / "match.json").read_text())
    aud = pd.read_csv(origen / "auditoria.csv") if (origen / "auditoria.csv").exists() else pd.DataFrame()
    res = ResultadoMatching(
        banci=pd.read_parquet(origen / "banci.parquet"),
        fubs_matcheados=set(datos["fubs_matcheados"]),
        mapa_tipo_match=datos["mapa_tipo_match"],
        auditoria=aud,
        verif_fecha=pd.read_parquet(origen / "verif_fecha.parquet"),
        candidatos=pd.read_parquet(origen / "candidatos_revision.parquet"),
    )
    deps = json.loads((origen / "huella.json").read_text(encoding="utf-8"))["dependencias"]
    return res, deps


def limpiar_cache(cfg: Settings, nivel: str = "todo") -> None:
    """Borra el caché. nivel ∈ {'universo', 'matching', 'todo'}."""
    objetivos = {
        "universo": [cfg.cache_dir / "universo"],
        "matching": [cfg.cache_dir / "matching"],
        "todo": [cfg.cache_dir / "universo", cfg.cache_dir / "matching"],
    }[nivel]
    for d in objetivos:
        if d.exists():
            shutil.rmtree(d)
            print(f"🗑️  Eliminado {d}")


# ─────────────────────────────────────────────────────────────────────────────
def _max_fecha(df: pd.DataFrame, col: str) -> Optional[str]:
    if col not in df.columns:
        return None
    v = pd.to_datetime(df[col], errors="coerce").max()
    return v.strftime("%Y-%m-%d") if pd.notna(v) else None
