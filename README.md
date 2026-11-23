# Proyecto de procesamiento de datos de personas desaparecidas

Pipeline en Python y Jupyter para preparar, cruzar y analizar fuentes como RNPDNO,
BANCI y PUI, y generar indicadores y presentaciones. La lógica principal está en
`src/`; los notebooks de `notebooks/` orquestan las etapas.

## Requisitos

- Python 3.11 o posterior.
- Los archivos de datos de entrada y, para el modo Drive, credenciales de Google.

Los datos fuente, resultados y credenciales no se distribuyen en este repositorio.
`input/`, `output/` y `.secrets/` están excluidos de Git. Solicita los insumos a sus
responsables y consulta [Fuentes de información](docs/1_fuentes_de_informacion.md)
para conocer los archivos que requiere cada etapa.

## Instalación

Desde la raíz del proyecto, crea y activa un entorno virtual e instala las dependencias:

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

```bash
# macOS / Linux
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Para contribuir con cambios en notebooks, configura el filtro que elimina sus
salidas al guardarlos en Git:

```bash
python -m nbstripout --install
```

## Preparar los insumos

Hay dos opciones para RNPDNO y PUI:

- **Google Drive:** copia `.secrets/drive.env.ejemplo` a `.secrets/drive.env`, agrega
  los identificadores de las carpetas y sigue el procedimiento de OAuth en
  [Configuración de Google Drive](docs/9_credenciales_google_drive.md). El archivo
  `oauth_client.json` se obtiene de Google Cloud; nunca lo subas al repositorio.
- **Archivos locales:** coloca los archivos autorizados en `input/` y configura
  `PIPELINE_MODO_INSUMOS=local`, `PIPELINE_RNPDNO_ARCHIVO` y
  `PIPELINE_PUI_ARCHIVO` según corresponda. En este modo el programa no descarga
  archivos ni comprueba si el corte es reciente. Consulta también
  [Flujo y pipeline](docs/2_flujo_y_pipeline.md).

BANCI, catálogos y otros insumos se proporcionan por separado y deben ubicarse en
las rutas indicadas en `config.py`. No se incluyen datos de ejemplo porque pueden
ser voluminosos o estar sujetos a controles de acceso.

## Ejecutar

Abre JupyterLab desde la raíz para ejecutar las celdas de los notebooks:

```bash
python -m jupyter lab
```

Ejecuta los notebooks ETL 1, 2 y 3 primero; el notebook 3 también necesita el
resultado del notebook 1. Después corre el notebook 4 para construir el universo
y los notebooks 5 o 6 para generar presentaciones. Los pasos y dependencias están
en [Flujo y pipeline](docs/2_flujo_y_pipeline.md).

Con los Parquet requeridos ya generados, también puedes consultar o construir el
caché sin abrir Jupyter:

```bash
python -m src.pipeline info --perfil reporte_diario
python -m src.pipeline build --perfil reporte_diario
```

Las pruebas unitarias se ejecutan con:

```bash
python -m unittest discover -s tests
```

Los resultados y el caché se guardan en `output/` y se regeneran localmente. No
se necesita Docker: el procesamiento depende de insumos externos que no forman
parte de la imagen ni del repositorio, y la autenticación de Drive utiliza OAuth
interactivo.

## Documentación

- [Fuentes de información](docs/1_fuentes_de_informacion.md)
- [Flujo y pipeline](docs/2_flujo_y_pipeline.md)
- [Metodología de matching](docs/3_metodologia_de_matching.md)
- [Generación de reportes](docs/4_generacion_de_reportes.md)
- [Arquitectura](docs/6_arquitectura.md)
- [Configuración de Google Drive](docs/9_credenciales_google_drive.md)
