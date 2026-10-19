"""Porcentajes de una partición que suman exactamente 100%.

`Universo.porcentaje` redondea cada porcentaje por su lado, y así la suma de los
recuadros de una lámina puede quedar en 99.9% o 100.1%: tres partes de 33.35%
redondean las tres hacia arriba. Aquí las décimas se reparten por resto mayor
(método de Hamilton): cada parte recibe su porcentaje truncado y las décimas que
faltan para el 100% van a las de mayor residuo. Ninguna parte se aleja más de
una décima de su valor exacto.

Vive aparte de src/utils.py por la misma razón que src/cortes_referencia.py:
`src.pipeline.universo` importa `src.utils`, así que ese archivo entra en la
huella de código del caché (`huella.RAICES`). Nada del pipeline importa este
módulo: tocarlo no invalida el caché.
"""

from __future__ import annotations

from typing import Iterable

from src.slices import Slice


def porcentajes_particion(universo, partes: Iterable[Slice], denominador: Slice,
                          sufijo: str = "", decimales: int = 1) -> dict[str, str]:
    """`pct_<nombre><sufijo>` de cada parte contra `denominador`, sumando 100%.

    Las partes tienen que repartirse el denominador sin huecos ni traslapes. Si
    sus conteos no suman el del denominador, forzar el 100% escondería esa
    diferencia en las décimas, así que se detiene.

    `sufijo` es el que distingue al marcador en la plantilla cuando la misma
    rebanada aparece en otra lámina contra otro denominador (`_v1`, `_v2`, …).
    Las décimas sobrantes se reparten en el orden de `partes` si dos residuos
    empatan.
    """
    partes = list(partes)
    conteos = [universo.contar(s) for s in partes]
    total = universo.contar(denominador)
    if sum(conteos) != total:
        detalle = "\n".join(f"     {s.nombre}: {n:,}" for s, n in zip(partes, conteos))
        raise ValueError(
            f"❌ Las partes no suman el denominador {denominador.nombre} ({total:,}):\n"
            f"{detalle}\n"
            f"     suma: {sum(conteos):,}\n"
            f"   Sus porcentajes no pueden sumar 100% sin falsear alguno."
        )

    claves = [f"pct_{s.nombre}{sufijo}" for s in partes]
    if total == 0:
        return dict.fromkeys(claves, "n/d")

    # Todo en enteros —unidades de la última cifra: 1000 décimas = 100%— para
    # que ni el truncado ni la comparación de residuos dependan de flotantes.
    escala = 100 * 10 ** decimales
    unidades, residuos = map(list, zip(*(divmod(escala * n, total) for n in conteos)))
    faltan = escala - sum(unidades)
    # `sorted` es estable también con reverse=True: un empate favorece a la
    # parte declarada primero.
    for i in sorted(range(len(partes)), key=residuos.__getitem__, reverse=True)[:faltan]:
        unidades[i] += 1

    return {clave: f"{u / 10 ** decimales:.{decimales}f}%"
            for clave, u in zip(claves, unidades)}
