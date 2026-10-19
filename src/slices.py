"""CAPA C · Rebanadas declarativas.

Sustituye a la grilla `COMBINACIONES_A_GENERAR` + `buscar_dataframe()`. Antes se
generaban archivos Parquet y se les buscaba por subcadena del nombre; ahora el
notebook que arma la PPT declara con objetos tipados exactamente lo que necesita
y nada más se calcula:

    from src.slices import Slice
    REQUERIDOS = [
        Slice("rn",       "01oct24-max"),
        Slice("rn",       "01oct24-max", estatus="des"),
        Slice("rn-si-ba", "01oct24-max", estatus="des", estado=17),
    ]

`Slice.nombre` conserva la nomenclatura de catalogo_abreviaturas.md
(`reg_rn-si-ba_01oct24-max_des`), así que los nombres de indicador que consumen
las plantillas PPTX no cambian. La diferencia es que ahora se derivan de un
objeto validado en vez de parsearse de un nombre de archivo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import config

# Bases del catálogo. El valor indica sobre qué frame del universo se resuelven
# y con qué máscara de pertenencia.
BASES = {
    "rn":       ("rn", None),
    "ba":       ("ba", None),
    "rn-no-ba": ("rn", ("in_banci_derivada_rnpdno_banci", False)),
    "rn-si-ba": ("rn", ("in_banci_derivada_rnpdno_banci", True)),
    "ba-no-rn": ("ba", ("in_rnpdno_derivada_rnpdno_banci", False)),
    "ba-si-rn": ("ba", ("in_rnpdno_derivada_rnpdno_banci", True)),
}

ESTATUS = {"all", "des", "loc"}


@dataclass(frozen=True, order=True)
class Slice:
    """Una rebanada del universo. Inmutable y hashable: sirve como llave de dict."""

    base: str = "rn"
    periodo: str = "min-max"
    estatus: str = "all"
    # Puede combinar varias banderas separadas por "_": "sfval_ccvac" exige ambas.
    subfiltro: str = "all"
    estado: Optional[int] = None

    def __post_init__(self):
        if self.base not in BASES:
            raise ValueError(f"Base '{self.base}' desconocida. Válidas: {sorted(BASES)}")
        if self.estatus not in ESTATUS:
            raise ValueError(f"Estatus '{self.estatus}' desconocido. Válidos: {sorted(ESTATUS)}")
        if self.estado is not None and self.estado not in config.ENTIDADES:
            raise ValueError(
                f"Entidad {self.estado} desconocida. Válidas: 1–{max(config.ENTIDADES)}"
            )

    @property
    def nombre(self) -> str:
        """Nombre canónico del indicador (nomenclatura de catalogo_abreviaturas.md)."""
        partes = ["reg", self.base, self.periodo]
        if self.estatus != "all":
            partes.append(self.estatus)
        if self.subfiltro != "all":
            partes.append(self.subfiltro)
        if self.estado is not None:
            partes.append(f"ent{self.estado:02d}")
        return "_".join(partes)

    @property
    def entidad_texto(self) -> str:
        return config.ENTIDADES.get(self.estado, "Nacional") if self.estado else "Nacional"

    def con(self, **cambios) -> "Slice":
        from dataclasses import replace
        return replace(self, **cambios)

    def por_entidad(self, cve: int) -> "Slice":
        """Misma rebanada acotada a una entidad. Atajo para las PPT estatales."""
        return self.con(estado=cve)

    @property
    def padre(self) -> "Slice":
        """Rebanada denominadora: la misma sin su ÚLTIMO filtro.

        Es la regla de los marcadores `pct_*` de las plantillas: cada porcentaje
        se lee contra su nivel inmediato superior.

            reg_rn_01oct24-max_loc_cdel  →  reg_rn_01oct24-max_loc
            reg_rn_01oct24-max_loc       →  reg_rn_01oct24-max
            reg_rn_01oct24-max           →  reg_rn_min-max

        Se quita, en este orden: entidad → último subfiltro → estatus → período.
        """
        if self.estado is not None:
            return self.con(estado=None)
        if self.subfiltro != "all":
            tokens = self.subfiltro.split("_")[:-1]
            return self.con(subfiltro="_".join(tokens) if tokens else "all")
        if self.estatus != "all":
            return self.con(estatus="all")
        return self.con(periodo="min-max")

    @classmethod
    def desde_nombre(cls, nombre: str) -> "Slice":
        """Reconstruye un Slice a partir de su nombre canónico.

        Puente para el código que todavía trabaja con las cadenas antiguas.
        """
        tokens = nombre.split("_")
        if tokens and tokens[0] == "reg":
            tokens = tokens[1:]
        if len(tokens) < 2:
            raise ValueError(f"Nombre de rebanada no reconocido: {nombre!r}")

        base, periodo, resto = tokens[0], tokens[1], tokens[2:]
        estatus, estado, subs = "all", None, []
        for t in resto:
            if t in ESTATUS:
                estatus = t
            elif t.startswith("ent") and t[3:].isdigit():
                estado = int(t[3:])
            else:
                subs.append(t)
        return cls(base=base, periodo=periodo, estatus=estatus,
                   subfiltro="_".join(subs) if subs else "all", estado=estado)

    def __str__(self) -> str:
        return self.nombre


def expandir_entidades(base: Slice, entidades=None) -> list[Slice]:
    """Una rebanada por entidad federativa, para las 32 PPT estatales.

    Todas se resuelven sobre el MISMO universo en memoria: son 32 máscaras
    booleanas, no 32 corridas de matching.
    """
    claves = entidades if entidades is not None else sorted(config.ENTIDADES)
    return [base.por_entidad(c) for c in claves]
