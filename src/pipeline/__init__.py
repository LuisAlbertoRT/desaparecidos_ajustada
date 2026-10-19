"""Pipeline de indicadores, dividido en tres capas por costo de cómputo.

    A. matching   (minutos)      → src.pipeline.motores
    B. derivadas  (segundos)     → src.pipeline.derivadas
    C. rebanadas  (microsegundos)→ src.slices

`src.pipeline.universo.Universo` orquesta A y B con caché en disco (ver
`src.pipeline.huella` para lo que decide si un caché sigue valiendo); los
notebooks de PPT sólo consumen C.
"""

from src.pipeline.universo import Universo   # noqa: F401
