"""Reglas de invalidación, como funciones registradas.

Cada regla es una función pura registrada con `@regla_motor` o `@regla_rnpdno`.
El perfil las activa por nombre en `reglas_post`, en orden:

    reglas_post = ["excluir_revision_manual", "regla_r_desfase_dias"]

Así se obtienen variantes del pipeline (distintos criterios de match confirmado)
sin bifurcar el notebook 4 en 4_a / 4_b / 4_c, y sin que el resto del código se
entere. Agregar una regla nueva = escribir una función y nombrarla en un perfil.

POR QUÉ SE APLICAN POR MOTOR Y ANTES DE LA CASCADA
--------------------------------------------------
Antes se aplicaban DESPUÉS de consolidar, sobre el match ganador. Eso rompía la
cascada: si el estándar ganaba y la regla lo invalidaba, la fila quedaba en
`sin_match` aunque el manual o el refinado tuvieran un match válido esperando
detrás. Un match anulado no debe matar la fila, debe ceder el turno.

Aplicándolas por motor y antes de consolidar, la prioridad hace lo que promete:
cada método se ofrece con sus matches ya depurados y el siguiente entra si el
anterior no dejó ninguno válido. Un match confirmado a mano ya no puede ser
tumbado por un match estándar que la regla R descarta.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

# nombre → función. Las de MOTOR corren sobre las columnas de cada motor, antes de
# la cascada (capa A); las de RNPDNO corren al derivar banderas (capa B), cuando ya
# se conocen los FUBs matcheados.
REGLAS_MOTOR: dict[str, Callable] = {}
REGLAS_RNPDNO: dict[str, Callable] = {}


def regla_motor(nombre: str):
    def deco(fn):
        REGLAS_MOTOR[nombre] = fn
        return fn
    return deco


def regla_rnpdno(nombre: str):
    def deco(fn):
        REGLAS_RNPDNO[nombre] = fn
        return fn
    return deco


def _anular_motor(banci: pd.DataFrame, mask, motor: str, motivo: str = "") -> None:
    """Deja a ESE motor sin match en las filas marcadas. La fila sigue viva: los
    demás motores conservan los suyos y la cascada les dará su turno.

    Antes de borrar, la oferta anulada se copia a `*_anulado`. Anular sin dejar
    rastro perdía el único registro de por qué una fila quedó sin match: los
    candidatos `revision manual` del refinado —que son precisamente la cola que
    alguien tiene que trabajar a mano— desaparecían del resultado y ya no se
    podían distinguir de las filas donde ningún motor encontró nada. Las columnas
    `*_anulado` NO participan en la cascada: son evidencia, no oferta.
    """
    col_tipo_anulado = f"tipo_match_{motor}_anulado"
    col_id_anulado = f"id_match_{motor}_anulado"
    col_motivo = f"motivo_anulacion_{motor}"
    for col in (col_tipo_anulado, col_id_anulado, col_motivo):
        if col not in banci.columns:
            banci[col] = None

    banci.loc[mask, col_tipo_anulado] = banci.loc[mask, f"tipo_match_{motor}"]
    banci.loc[mask, col_id_anulado] = banci.loc[mask, f"id_match_{motor}"]
    banci.loc[mask, col_motivo] = motivo or "anulada"

    banci.loc[mask, f"tipo_match_{motor}"] = "sin_match"
    banci.loc[mask, f"id_match_{motor}"] = None


# ─────────────────────────────────────────────────────────────────────────────
# Reglas por MOTOR (capa A, antes de la cascada)
#
# Firma: (banci, rn, cfg, motor, verbose) -> banci
# Cada una anula los matches inválidos DE ESE MOTOR. Nunca toca la fila entera:
# los demás motores conservan los suyos y la prioridad decide después.
# ─────────────────────────────────────────────────────────────────────────────
@regla_motor("excluir_revision_manual")
def _excluir_revision_manual(banci: pd.DataFrame, rn: pd.DataFrame, cfg,
                             motor: str, verbose=True) -> pd.DataFrame:
    """Los candidatos 'revision manual' del refinado no son matches confirmados.

    En normalizar_folios_v6.py van a revision_manual_v6.xlsx para validación
    humana. Aquí se retiran de la oferta del motor que los produjo, así que la
    cascada ni siquiera los considera.
    """
    col_tipo = f"tipo_match_{motor}"
    if col_tipo not in banci.columns:
        return banci
    mask = banci[col_tipo] == "revision manual"
    n = int(mask.sum())
    if n:
        if verbose:
            print(f"  🔻 excluir_revision_manual [{motor}]: {n:,} candidatos sin validar.")
        _anular_motor(banci, mask, motor, motivo="revision manual")
    return banci


@regla_motor("regla_r_desfase_dias")
def _regla_r_desfase_dias(banci: pd.DataFrame, rn: pd.DataFrame, cfg,
                          motor: str, verbose=True) -> pd.DataFrame:
    """Regla R estricta: descarta los matches de ESTE motor con desfase de fecha de
    desaparición mayor a la tolerancia, o cuyo FUB está Localizado en el RNPDNO.

    El desfase sólo se evalúa donde el motor lo reporta (`diferencia_dias_*`); la
    condición de FUB Localizado aplica a cualquier motor.
    """
    col_id, col_tipo = f"id_match_{motor}", f"tipo_match_{motor}"
    if col_id not in banci.columns or col_tipo not in banci.columns:
        return banci

    activo = banci[col_tipo] != "sin_match"
    mask = pd.Series(False, index=banci.index)
    motivos = []

    col_dif = f"diferencia_dias_desaparicion_{motor}"
    if col_dif in banci.columns:
        dif = pd.to_numeric(banci[col_dif], errors="coerce").abs()
        m_dif = activo & (dif > cfg.tolerancia_desfase_dias)
        mask |= m_dif
        if int(m_dif.sum()):
            motivos.append(f"desfase > {cfg.tolerancia_desfase_dias}d: {int(m_dif.sum()):,}")

    # Sin un `if` que la salte: si faltara la clasificación, la regla dejaría de
    # aplicarse en silencio. El contrato de Resultado_1 garantiza las dos columnas.
    mapa = (rn.drop_duplicates(subset=["fub_rnpdno"])
              .set_index("fub_rnpdno")["clasificacion_des_derivada_rnpdno"])
    m_loc = activo & (banci[col_id].map(mapa) == "Localizados")
    mask |= m_loc
    if int(m_loc.sum()):
        motivos.append(f"FUB Localizado: {int(m_loc.sum()):,}")

    n = int(mask.sum())
    if n:
        if verbose:
            print(f"  🔻 regla_r_desfase_dias [{motor}]: {n:,} matches excluidos "
                  f"({'; '.join(motivos)}).")
        _anular_motor(banci, mask, motor, motivo="; ".join(motivos) or "regla R")
    return banci


# ─────────────────────────────────────────────────────────────────────────────
# Reglas sobre RNPDNO (capa B, con los FUBs ya consolidados)
# ─────────────────────────────────────────────────────────────────────────────
@regla_rnpdno("actualizar_rn_con_banci")
def _actualizar_rn_con_banci(rn: pd.DataFrame, fubs: set[str], cfg, verbose=True) -> pd.DataFrame:
    """Un FUB reclamado por BANCI se considera de fiscalía.

    No toca `dependencia_origen_rnpdno`, que es el dato tal como vino: escribe la
    corrección en `dependencia_origen_derivada_rnpdno_banci`.
    """
    rn["dependencia_origen_derivada_rnpdno_banci"] = rn["dependencia_origen_rnpdno"]
    mask = rn["fub_rnpdno"].astype(str).isin(fubs)
    rn.loc[mask, "dependencia_origen_derivada_rnpdno_banci"] = "FISCALIA GENERAL (BANCI MATCH)"
    if verbose:
        print(f"  ↻ actualizar_rn_con_banci: {int(mask.sum()):,} registros RNPDNO actualizados.")
    return rn


# ─────────────────────────────────────────────────────────────────────────────
def aplicar_reglas_motores(banci: pd.DataFrame, rn: pd.DataFrame, cfg,
                           motores: list[str], verbose=True) -> pd.DataFrame:
    """Aplica las reglas activas del perfil a CADA motor, antes de consolidar.

    El orden importa dos veces: el de `reglas_post` (qué se descarta primero) y el
    de `motores`, que es el de la cascada. Al depurar la oferta de cada motor antes
    de elegir ganador, un match anulado cede el turno al siguiente método en vez de
    dejar la fila sin match.
    """
    activas = [n for n in cfg.reglas_post if n in REGLAS_MOTOR]
    desconocidas = [n for n in cfg.reglas_post
                    if n not in REGLAS_MOTOR and n not in REGLAS_RNPDNO]
    if desconocidas:
        raise KeyError(
            f"Reglas desconocidas en el perfil '{cfg.perfil}': {desconocidas}. "
            f"Disponibles: {sorted(set(REGLAS_MOTOR) | set(REGLAS_RNPDNO))}"
        )
    if activas and verbose:
        print(f"\n🧹 Reglas de invalidación por motor: {' → '.join(activas)}")
    for nombre in activas:
        for motor in motores:
            banci = REGLAS_MOTOR[nombre](banci, rn, cfg, motor, verbose=verbose)
    return banci


def aplicar_reglas_rnpdno(rn: pd.DataFrame, fubs: set[str], cfg, verbose=True) -> pd.DataFrame:
    for nombre in cfg.reglas_post:
        if nombre in REGLAS_RNPDNO:
            rn = REGLAS_RNPDNO[nombre](rn, fubs, cfg, verbose=verbose)
    return rn
