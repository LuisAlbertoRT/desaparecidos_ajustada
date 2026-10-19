# Proyecto de Desaparecidos

Este repositorio contiene el pipeline de procesamiento, integración, análisis y visualización de información sobre personas desaparecidas, centralizando fuentes como RNPDNO, BANCI y PUI (Plataforma Única de Identidad).

## Objetivo del Proyecto

El objetivo principal de este proyecto es realizar la limpieza, cruce (matching) y conciliación de bases de datos de personas desaparecidas para la generación de indicadores analíticos y presentaciones automatizadas (diapositivas) a nivel estatal y nacional.

## Estructura Principal del Proyecto

```text
desaparecidos/
├── 1_funciones/       # Scripts de visualización (barras, líneas, treemaps)
├── docs/              # Documentación detallada del proyecto
├── input/             # Bases de datos y catálogos fuente (RNPDNO, BANCI, PUI, INEGI)
├── notebooks/         # Interfaz ejecutable: ETL y notebooks que arman cada PPT
├── output/            # Resultados y caché regenerable del pipeline
├── perfiles/          # Configuración como datos: un TOML por variante de reporte
└── src/               # Lógica del proyecto (pipeline, matching, limpieza, PPT)
```

## Configuración y Requisitos

Para ejecutar el pipeline, se recomienda utilizar un entorno virtual de Python.

1.  Instalar las dependencias del proyecto:
    ```bash
    pip install -r requirements.txt
    ```
2.  Ajustar rutas base y catálogos en `config.py` solo si cambia la infraestructura.
3.  Para configurar una corrida (archivo fuente, reglas, entidad, períodos), editar o crear
    un perfil en [`perfiles/`](perfiles/) — no `config.py`.

## Pipeline de Ejecución

**1. Fase ETL** — cada notebook deja un Parquet de nombre fijo en `output/`

| Notebook | Salida |
|---|---|
| `1_Procesamiento_ETL_RNPDNO.ipynb` | `Resultado_1_Procesamiento_ETL_RNPDNO.parquet` |
| `2_Procesamiento_ETL_BANCI.ipynb` | `Resultado_2_Procesamiento_ETL_BANCI.parquet` |
| `3_Procesamiento_ETL_PUI.ipynb` | `Resultado_3_Procesamiento_ETL_PUI.parquet` |

Los tres son independientes entre sí, con una excepción: **el 3 necesita el Parquet del 1**
(usa el RNPDNO para resolver clasificación, fecha de hechos y CURP).

El notebook 3 consolida las tres entregas de la PUI —coincidencias administrativas,
confrontas manuales y defunciones— en una marca por persona. Es el origen de las banderas
`cind` / `sind` y, con ellas, de los indicadores de *información suficiente*
(`sisf` / `cisf`). El recorrido completo, desde el archivo de entrada hasta el marcador de
la plantilla, está en [`docs/8_indicios_de_vida.md`](docs/8_indicios_de_vida.md).

**2. Fase de análisis y reportes**

*   `4_Generacion_Indicadores.ipynb`: construye el **universo** (RNPDNO + BANCI cruzados,
    con banderas derivadas) y lo deja cacheado.
*   `5_PPT_Reporte_Estatal.ipynb` y `6_PPT_Reporte_Diario.ipynb`: **consumen** ese universo.
    Cada uno declara su perfil de configuración y la lista de rebanadas que necesita.

Los notebooks de PPT no dependen entre sí y pueden ejecutarse en cualquier orden: el
primero que corra construye el universo, los siguientes lo leen del caché. Si entre uno y
otro cambia `config.py`, el perfil, el código o un insumo, el caché ya no vale y el
siguiente lo recalcula.

### Configuración por perfiles

La configuración variable no vive en `config.py` sino en `perfiles/*.toml`. `config.py`
conserva solo lo invariante (rutas base, mapeos de columnas, catálogos de regex, entidades).

```python
from src.settings import Settings
from src.pipeline import Universo
from src.slices import Slice

cfg = Settings.desde_perfil("reporte_diario")
u   = Universo.construir(cfg)          # acierto de caché si ya se construyó

u.contar(Slice("rn", "01oct24-max", estatus="des"))            # nacional
u.contar(Slice("rn", "01oct24-max", estatus="des", estado=17)) # Morelos
```

Dos perfiles pueden coexistir en el mismo kernel; ya no hace falta editar `config.py`
ni hacer `importlib.reload`.

### Las tres capas y el caché

| Capa | Qué hace | Costo | Se invalida con |
|---|---|---|---|
| A. Matching | carga de fuentes, 3 motores, reglas, cascada | minutos | perfil, `config.py`, código de los motores, insumos leídos |
| B. Derivadas | banderas `is_*`, dimensiones de rebanada | segundos | lo anterior + modalidad de carpeta + código de las derivadas |
| C. Rebanadas | máscaras por base/período/estatus/subfiltro/entidad | µs | nada |

Cambiar período, estatus, subfiltro o entidad **no vuelve a ejecutar el matching**.
La entidad dejó de ser un filtro previo a los motores y ahora es una dimensión de corte,
así que una sola corrida alimenta las 32 PPT estatales.

Para precalentar el caché fuera de Jupyter:

```bash
python -m src.pipeline info  --perfil reporte_diario
python -m src.pipeline build --perfil reporte_diario
```

Detalle completo en [`docs/6_arquitectura.md`](docs/6_arquitectura.md).

### El cruce BANCI ↔ RNPDNO en una tabla

Tres motores corren **siempre y sobre el universo completo**; la cascada decide después
quién se queda con cada expediente. `manual` va primero: cuando una revisión humana y el
algoritmo señalan a personas distintas, gana la revisión.

| Motor | Cómo decide | Gana |
|---|---|---:|
| **manual** | pares que el SESNSP validó uno por uno | 561 |
| **estandar** | embudo FUB → CURP → nombre corroborado | 6,082 |
| **refinado** | folio de carpeta normalizado + guardianes anti-homónimo | 5,243 |
| *sin match* | permanece sólo en BANCI | 22,891 |

Metodología completa en [`docs/3_metodologia_de_matching.md`](docs/3_metodologia_de_matching.md).

## Manual de Usuario y Documentación Detallada

Este repositorio cuenta con un **Manual de Usuario Conceptual** integrado para comprender las lógicas institucionales, los universos de datos y la metodología de unificación (matching) sin necesidad de revisar líneas de código.

*   [Manual de Usuario Conceptual: Lógicas de Procesamiento y Universos de Información](#manual-de-usuario-conceptual-lógicas-de-procesamiento-y-universos-de-información)

Para comprender a fondo la metodología técnica y la arquitectura del proyecto, consulta la documentación detallada en la carpeta [`docs/`](docs/):

1.  [Fuentes de Información y Catálogos](docs/1_fuentes_de_informacion.md)
2.  [Flujo y Pipeline de Datos](docs/2_flujo_y_pipeline.md)
3.  [Metodología de Matching](docs/3_metodologia_de_matching.md)
4.  [Generación de Reportes y Visualización](docs/4_generacion_de_reportes.md)
5.  [Diccionario de Variables](docs/5_diccionario_de_variables.md)
6.  [Arquitectura del Repositorio](docs/6_arquitectura.md)
7.  [Llaves de cruce entre BANCI y RNPDNO](docs/7_llaves_de_cruce.md)
8.  [Indicios de vida: del ETL de PUI al indicador](docs/8_indicios_de_vida.md)

La nomenclatura de los marcadores (`reg_rn_01oct24-max_des`…) vive aparte, en
[`catalogo_abreviaturas.md`](catalogo_abreviaturas.md).
