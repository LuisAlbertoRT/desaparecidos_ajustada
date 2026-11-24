# ————————————————————————————————————————————————————————— #
# Nombre: Jocelyn Rocha
# Contacto: jocelyn.flores@transformaciondigital.com.mx
# Script: funcion_actualizar_rnpdno_y_procesar_variables.R
# Proyecto: Personas desaparecidas
# Fecha: 2026-05-08
# Propósito: Función de descarga del RNPDNO (opcional) y de procesamiento de variables.
# ————————————————————————————————————————————————————————— #
# Preámbulo -----
# ————————————————————————————————————————————————————————— #

## ----- DESCARGA DEL RNPDNO (OPCIONAL) -----

# Requerimientos para correr la función automatizar_base_final_rnpdno():

# 1. Acceso a las carpetas de trabajo: se requiere el acceso a la carpeta de Google Drive que contiene el archivo .xlsx denominado "reporte_personas" (equipo respondable: Mario y Gerardo). Se necesita adicionalmente el ID de la carpeta en donde se guarda este archivo.

# 2. Archivos en donde se realiza la validación con las curps, estos archivos se encuentran en la carpeta de "input" (CURP_act260525, curps_con_resultado_prueba_050825, curps_con_resultado_prueba_01072025, curps_reconstruidas_210625).

# Este código está integrado por partes: 

# a. La primera es opcional. Este tiene el objetivo de automatizar la descarga del archivo, realizar la limpieza correspondiente, ejecutar los cruces de información con los curps y generar el acomodo de la base final. La base procesada se almacena en la carpeta "output" del proyecto y el archivo en formato .parquet se guarda bajo el nombre "base_final_reporte_personas_ddmmaaaa".

# b. La segunda parte se encarga de realizar limpieza y generar nuevas columnas que serán de ayuda para realizar conteos y tabulados. La función procesamiento_base_final() realiza las siguientes transformaciones:

# sobre la base del RNPDNO:
#
# Variables ajustadas:
#   - fechanacimiento:    se convierte a Date con lubridate::as_date()
#   - fechahechos, fechalocaliza, fechapercato, fechacaptura: se convierten a Date
#   - fechalocaliza:      se invalida (NA) si es anterior a fechahechos o posterior
#                         a fecha_corte
#   - fecha_hechos_modificada: se corrige si es posterior a fechalocaliza_imputada
#   - idestado:           se convierte a character y se rellena con str_pad (2 dígitos)
#   - idestadonacimiento_vic: se rellena with str_pad (2 dígitos)
#   - idmunicipio:        se rellena with str_pad (3 dígitos)
#   - indicadora_indicio_de_vida: se reclasifica unificando "defuncion" y
#                                 "con registro administrativo en PUI" como
#                                 "con registro administrativo"
#   - curp_victima:       se elimina si es inválida (queda NA)
#
# Variables creadas:
#   - clasificacion_des:          "Desaparecidos", "Pendientes" o "Localizados"
#   - fecha_hechos_modificada:    coalesce de fechahechos, fechapercato, fechacaptura
#   - anio_localizado:            año de fechalocaliza
#   - anio_hechos:                año de fechahechos
#   - anio_hechos_modificada:     año de fecha_hechos_modificada
#   - mes_hechos_modificada:      mes de fecha_hechos_modificada
#   - anio_mes_hechos_modificada: fecha truncada a mes (año-mes-01)
#   - fechalocaliza_imputada:     imputada con fecha_hechos_modificada si Localizado
#   - anio_loc_imputada:          año de fechalocaliza_imputada
#   - mes_loc_imputada:           mes de fechalocaliza_imputada
#   - anio_mes_loc_imputada:      fecha truncada a mes (año-mes-01)
#   - indicadora_carpeta:         "Con carpeta" / "Sin carpeta"
#   - expediente_reclasif:        "carpeta de investigacion" / "expediente genérico"
#   - dependencia_origen_reclasificado: fiscalías, comisiones y portal homologados
#   - indicadora_curp_valida:     "valida" / "invalida"
#   - estado_desaparicion:        nombre del estado (join con catálogo INEGI)
#   - entidad_nacimiento_nom:     nombre del estado de nacimiento (join con catálogo INEGI)
#   - cvegeo:                     concatenación de idestado + idmunicipio (5 dígitos)
#   - cvegeo_desaparicion:        renombre de cvegeo
#   - cve_estado_desaparicion:    renombre de idestado
#   - cve_municipio_desaparicion: renombre de idmunicipio
#   - municipio_desaparicion:     nombre del municipio (join con catálogo INEGI)
#   - edad_al_momento_desaparicion: diferencia en años entre fecha_hechos_modificada
#                                   y fechanacimiento
#   - grupo_etario:               factor ordenado de 5 categorías etarias

# ————————————————————————————————————————————————————————— #
# Librerías -----
# ————————————————————————————————————————————————————————— #

setwd(here::here("RNPDNO"))

pacman::p_load(openxlsx, 
               readr,
               tidyverse,
               dplyr, 
               lubridate, # Librería para trabajar con fechas y horas
               readxl,
               zoo, # Librería para trabajar con series de tiempo y fechas
               janitor, # Librería para limpiar y organizar datos
               purrr, # Librería para manejar listas y funciones de manera funcional/iterada
               googledrive, # Librería para descargar archivos de Google Drive
               fs, # Librería para manejar archivos y directorios de manera indirecta
               here, # Librería para manejar rutas de archivos 
               arrow # Librería para crear archivos Parquet
              )

# ————————————————————————————————————————————————————————— #
# Funciones y catálogos -----
# ————————————————————————————————————————————————————————— #

## ---- Catálogos de INEGI ----- ##

# Entidades
load(here::here("RNPDNO", "input", "catalogos_inegi", "cat_ent.R"))

catalogo_estados_inegi <- cat_ent
rm(cat_ent)

# Municipios
catalogo_municipios_inegi_path <- dir_ls(here::here(), recurse = TRUE, glob = "*catalogos_ingei/catalogo_municipios_inegi.csv")
catalogo_municipios_inegi <- read_csv(catalogo_municipios_inegi_path)

## ---- Regex usadas en la validación de curps ------ ##
curp_regex <- "^[A-Z]{4}\\d{6}[HM]"
curp_regex2 <- "[A-Z]{3}.{2}$"

# Códigos de estado válidos en las curps
codigos_validos_curp <- c(
  "AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR",
  "HG", "JC", "MC", "MN", "MS", "NT", "NL", "OC", "PL", "QT", "QR", "SP",
  "SL", "SR", "TC", "TS", "TL", "VZ", "YN", "ZS", "NE")

#' Validar si una CURP cumple el formato esperado
#'
#' @param curp Vector de tipo character con la(s) CURP(s) a validar.
#' @return Vector lógico (misma longitud que `curp`): TRUE si `curp` cumple el
#'   patrón general de una CURP (`curp_regex`), termina con el patrón
#'   `curp_regex2`, tiene exactamente 18 caracteres y su código de entidad
#'   (posiciones 12-13) está en `codigos_validos_curp`; FALSE en caso
#'   contrario.
es_curp_valida <- function(curp) {
  grepl(curp_regex, curp, ignore.case = TRUE) &
    grepl(curp_regex2, curp, ignore.case = TRUE) &
    nchar(curp) == 18 &
    substr(curp, 12, 13) %in% codigos_validos_curp
}

#' Normalizar y homologar los nombres de `dependencia_origen`
#'
#' Convierte `dependencia_origen` a formato "Oración", detecta menciones de
#' nombres de entidades federativas (tolerando con/sin acento) y las
#' reemplaza por su versión oficial del catálogo INEGI, aplica una lista de
#' correcciones manuales para casos excepcionales (Fiscalía General de la
#' República, Estado de México, Nuevo León, CNB, Michoacán, Querétaro,
#' Portal, Yucatán) y capitaliza palabras clave (Búsqueda, Comisión, etc.).
#'
#' @param comprimido Data frame que contiene la columna `dependencia_origen`
#'   a limpiar.
#' @param catalogo_estados_inegi Data frame del catálogo de entidades del
#'   INEGI, con al menos la columna `nom_ent`.
#' @return `comprimido` con la columna `dependencia_origen` normalizada.
limpiar_dependencia_original <- function(comprimido, catalogo_estados_inegi) {

  # Hacer dependencia_origen str_to_sentence
  comprimido <- comprimido |> 
    mutate(
      dependencia_origen = str_to_sentence(dependencia_origen)
    )
  
  # Hacemos pull de las entidades de nom_ent de catalogo_estados_inegi
  catalogo_estados_inegi |> 
    pull(nom_ent) -> entidades_inegi

  # Función auxiliar: convierte un string a un patrón regex que acepta
  # la vocal con o sin acento (y ñ/n)
  flexibilizar_acentos <- function(texto) {
    texto |> 
    str_replace_all("a", "[aá]") |> 
    str_replace_all("e", "[eé]") |> 
    str_replace_all("i", "[ií]") |> 
    str_replace_all("o", "[oó]") |> 
    str_replace_all("u", "[uúü]") |> 
    str_replace_all("n", "[nñ]")
  }

  # Versión "base" de cada entidad: sin acentos, en minúsculas
  entidades_inegi_base <- entidades_inegi |> 
  stri_trans_general("Latin-ASCII") |> 
  str_to_lower()
  
  # Patrón regex flexible a acentos, uno por entidad (no combinado en una sola
  # alternación: se aplican uno por uno, ver nota de rendimiento abajo)
  patrones_por_entidad <- str_c("\\b(", flexibilizar_acentos(entidades_inegi_base), ")\\b")

  # Reemplazo: cada match (venga con o sin acento, en cualquier combinación
  # de mayúsculas/minúsculas) se normaliza a la versión oficial (con acento).
  # Se itera sobre las ~32 entidades y, en cada iteración, se aplica un
  # str_replace_all() con reemplazo fijo (sin función) — cada iteración es una
  # sola pasada vectorizada sobre toda la columna.
  dependencia_origen_normalizada <- comprimido$dependencia_origen
  for (i in seq_along(patrones_por_entidad)) {
    dependencia_origen_normalizada <- str_replace_all(
      dependencia_origen_normalizada,
      regex(patrones_por_entidad[i], ignore_case = TRUE),
      entidades_inegi[i]
    )
  }
  comprimido$dependencia_origen <- dependencia_origen_normalizada

  # Casos excepcionales. 
  # 
  # 1. Si dependencia_origen contiene "Fiscalia general de la republica" entonces reemplazar por "Fiscalía General de la República"
  # 2. Si dependencia_origen contiene "estado de mexico" hacer str_replace_all para reemplazar "estado de mexico" por "Estado de México"
  # 3. Si dependencia_origen contiene "nuevo leon" hacer str_replace_all para reemplazar "nuevo leon" por "Nuevo León"
  # Si dependencia_origen es igual a "Comision nacional de busqueda de personas" entonces reemplazar por "Comisión Nacional de Búsqueda de Personas"
  # 5. Si dependencia_origen es igual "michoacan" entonces reemplazar por "Michoacán"
  # 6. Si dependencia_origen es igual a "queretaro" entonces reemplazar por "Querétaro"
  # 7. Si dependencia_origen es igual a "Se Desconoce" entonces reemplazar por "Portal"
  # 8. Si dependencia_origen es igual a "yucatan" entonces reemplazar por "Yucatán"

  # Casos excepcionales
  comprimido <- comprimido |> 
  mutate(
    dependencia_origen = case_when(
      # 1. Fiscalía General de la República
      str_detect(dependencia_origen, regex("fiscalia general de la republica", ignore_case = TRUE)) ~ 
        "Fiscalía General de la República",
      
      # 2. Estado de México (reemplazar dentro del string)
      str_detect(dependencia_origen, regex("estado de m[eé]xico", ignore_case = TRUE)) ~ 
        str_replace_all(dependencia_origen, regex("estado de m[eé]xico", ignore_case = TRUE), "Estado de México"),
      
      # 3. Nuevo León (reemplazar dentro del string)
      str_detect(dependencia_origen, regex("nuevo le[oó]n", ignore_case = TRUE)) ~ 
        str_replace_all(dependencia_origen, regex("nuevo le[oó]n", ignore_case = TRUE), "Nuevo León"),
      
      # 4. Comisión Nacional de Búsqueda
      str_detect(dependencia_origen, regex("^comisi[oó]n nacional de b[uú]squeda", ignore_case = TRUE)) ~ 
        "Comisión Nacional de Búsqueda de Personas",
      
      # 5. Michoacán
      str_detect(dependencia_origen, regex("^michoac[aá]n$", ignore_case = TRUE)) ~ 
        "Michoacán",
      
      # 6. Querétaro
      str_detect(dependencia_origen, regex("^quer[eé]taro$", ignore_case = TRUE)) ~ 
        "Querétaro",
      
      # 7. Portal (Se desconoce)
      str_detect(dependencia_origen, regex("^se desconoce$", ignore_case = TRUE)) ~ 
        "Portal",
      
      # 8. Yucatán
      str_detect(dependencia_origen, regex("^yucat[aá]n$", ignore_case = TRUE)) ~ 
        "Yucatán",
      
      TRUE ~ dependencia_origen
    )
  )

  # Capitalizar palabras clave. Como las 7 palabras clave tienen una forma
  # "Title Case" fija y conocida de antemano, se itera sobre ellas y se aplica,
  # por cada una, un str_replace_all() con reemplazo fijo (sin función) — cada
  # iteración es una sola pasada vectorizada sobre toda la columna.
  palabras_clave <- c("local", "busqueda", "nacional", "general", "personas", "estado", "comision")

  dependencia_origen_capitalizada <- comprimido$dependencia_origen
  for (palabra in palabras_clave) {
    dependencia_origen_capitalizada <- str_replace_all(
      dependencia_origen_capitalizada,
      regex(str_c("\\b", palabra, "\\b"), ignore_case = TRUE),
      str_to_title(palabra)
    )
  }
  comprimido$dependencia_origen <- dependencia_origen_capitalizada

  comprimido <- comprimido |>
    mutate(
      dependencia_origen = str_replace_all(dependencia_origen, "Fiscalia", "Fiscalía"),
      dependencia_origen = str_replace_all(dependencia_origen, "Comision", "Comisión"),
      dependencia_origen = str_replace_all(dependencia_origen, "Busqueda", "Búsqueda")
    )
}

#' Conservar solo 3 carpetas de actualización por mes y borrar el resto
#'
#' Dentro de `ruta_guardado_folder` (una carpeta de mes), identifica las
#' subcarpetas `actualizacion_DD_MM_YYYY` y conserva únicamente la más
#' cercana al inicio del mes, la más cercana a la mitad del mes y la más
#' cercana al final del mes; el resto se elimina con `fs::dir_delete()`.
#'
#' @param ruta_guardado_folder Ruta (character) a la carpeta del mes que
#'   contiene las subcarpetas `actualizacion_*`.
#' @param mantener_ultimas Entero. Si hay `mantener_ultimas` carpetas o menos,
#'   no se borra nada. Default: 3.
#' @return `NULL` invisible si no hay nada que borrar. Cuando sí se borran
#'   carpetas, el efecto secundario es su eliminación en disco, con un
#'   `message()` que reporta cuántas se eliminaron.

# Nuevo parámetro 'tipo_archivo' para indicar si se trata de archivos de entrada o salida.
limpiar_actualizaciones_viejas_rnpdno <- function(ruta_guardado_folder, mantener_ultimas = 3, tipo_archivo = "entrada") {

  # Lista todas las subcarpetas "actualizacion_*" dentro del mes
  carpetas_actualizacion <- fs::dir_ls(
    ruta_guardado_folder, 
    type = "directory", 
    regexp = "actualizacion_"
  )
  
  # Si hay menos de tres archivos conservar todos
  if (length(carpetas_actualizacion) <= mantener_ultimas) {
    return(invisible(NULL))  # no hay nada que limpiar
  }

  if(tipo_archivo == "entrada") {
  # Solo mantener a las carpetas que estén más cerca del inicio, a la mitad y al final del mes
  # Extraemos la fecha del nombre de la carpeta para ordenar correctamente
  # (ordenar alfabéticamente NO funciona bien con fechas DDMMYYYY)
    
  # El formato de los archivos que se guardan en "input" lucen como:
  fechas <- stringr::str_extract(carpetas_actualizacion, "\\d{2}_\\d{2}_\\d{4}$") |>
     lubridate::dmy(quiet = TRUE)
  } else{
    # El formato de los archivos que se guardan en "output" lucen como:
    fechas <- str_extract(carpetas_actualizacion, "\\d{2}\\d{2}\\d{4}$") |> 
      dmy(quiet = TRUE)
  }

  # Ignorar carpetas cuyo nombre no siga el patrón "actualizacion_DD_MM_YYYY":
  # una sola fecha NA aquí arruinaría min()/max() para TODAS las carpetas
  if (any(is.na(fechas))) {
    warning("Se ignoraron carpetas con nombre inesperado (no siguen el patrón 'actualizacion_DD_MM_YYYY'): ",
            paste(carpetas_actualizacion[is.na(fechas)], collapse = ", "))
    carpetas_actualizacion <- carpetas_actualizacion[!is.na(fechas)]
    fechas <- fechas[!is.na(fechas)]
  }

  # Si después de filtrar quedan pocas carpetas válidas, no hay nada que limpiar
  if (length(carpetas_actualizacion) <= mantener_ultimas) {
    return(invisible(NULL))
  }

  # Fecha más cerca al inicio del mes
  fecha_inicio <- min(fechas)

  # Fecha más cercana del último día del mes
  fecha_fin <- max(fechas)

  # Fecha más cercana a la mitad del mes
  fecha_piso_mes <- floor_date(fecha_inicio, unit = "month")
  fecha_mitad_mes <- fecha_piso_mes + days(14)

  # Encontrar la fecha en 'fechas' más cercana a fecha_mitad_mes (vectorizado, usando abs() y which.min())
  diferencia_dias <- as.numeric(fecha_mitad_mes - fechas)
  fecha_mas_cercana_mitad <- fechas[which.min(abs(diferencia_dias))]

  # Ordenar archivos de menor a mayor
  orden <- order(fechas, decreasing = TRUE)
  carpetas_ordenadas <- carpetas_actualizacion[orden]
  
  # Nos quedamos con fecha_inicio , fecha_fin y fecha_mas_cercana_mitad
  fechas_a_conservar <- c(fecha_inicio, fecha_mas_cercana_mitad, fecha_fin)
  carpetas_a_borrar <- carpetas_actualizacion[!fechas %in% fechas_a_conservar]
  
  if (length(carpetas_a_borrar) > 0) {
    purrr::walk(carpetas_a_borrar, function(carpeta) {
      tryCatch({
        fs::dir_delete(carpeta)
        message("Se eliminó la carpeta de actualización vieja: ", carpeta)
      }, error = function(e) {
        warning("No se pudo eliminar '", carpeta, "' (¿sigue abierta o bloqueada?): ", conditionMessage(e))
      })
    })
  }
}

# ————————————————————————————————————————————————————————— #
# Bases de datos -----
# ————————————————————————————————————————————————————————— #

## ---- Registros administrativos manuales ----- ##

# Cambio al 17 de marzo de 2026: agreguemos los registros de personas desaparecidas con indicio de vida en PUI (sin indicios de vida en RNPDNO) que tienen su fub en los registros del RNPDNO
# Llamar de forma implícita a la carpeta 
# glob con "*" busca toda dirección con cola anterior a "resultados_13032026/registros_con_pui_13032026.xlsx"
registros_path <- dir_ls(here::here(), recurse = TRUE, glob = "*resultados_13032026/registros_con_pui_13032026.xlsx")
registros <- read_excel(registros_path)

## ---- Manejo de catálogos del INEGI ----- ##

# Crear nueva fila, donde cve_ent es 33 y nom_ent es "Nacido en el extranjero"
catalogo_estados_inegi <- catalogo_estados_inegi |> 
  clean_names() |>
  select(cve_ent, nom_ent) |>
  add_row(cve_ent = "33", nom_ent = "Se desconoce")

catalogo_estados_inegi <- catalogo_estados_inegi |> 
  mutate(cve_ent = as.character(cve_ent))

# Cargar catálogo de municipios de INEGI
catalogo_municipios_inegi <- read_csv(here::here("RNPDNO",
                                                 "input",
                                                 "catalogos_inegi",
                                                 "catalogo_municipios_inegi.csv"))

# ————————————————————————————————————————————————————————— #
# Función de descarga del RNPDNO (actualizar_base_final_rnpdno) -----
# ————————————————————————————————————————————————————————— #

#---------------#
## Paso 1. Descargar archivo de carpeta de Google Drive -----
#---------------#

# Se definen las cadenas de carácteres de las urls para la descarga del archivo desde Google Drive. Se recomienda no modificar estas cadenas, ya que son parte de la lógica para extraer los IDs necesarios para la descarga.
#' Obtener los IDs de Google Drive del archivo más reciente de una carpeta
#'
#' Busca dentro de `id_carpeta` el archivo (no carpeta) modificado más
#' recientemente y extrae tanto su ID completo (para `drive_download()`) como
#' su ID parcial (extraído de la URL de vista previa).
#'
#' @param id_carpeta Character. ID de la carpeta de Google Drive donde se
#'   busca el archivo.
#' @return Lista con `id_completo`, `id_parcial` y `nombre_archivo_encontrado`.
#'   Si ocurre un error (carpeta vacía, URL inválida, etc.) lo captura con
#'   `tryCatch()`, imprime el mensaje con `cat()` y regresa `NULL`.
obtener_ids_reporte_unico <- function(id_carpeta) {
  tryCatch({
    #Se busca el elemento más reciente dentro de la carpeta
    reporte_info <- drive_find(
      q = paste0('parents in "', id_carpeta, '" and mimeType != "application/vnd.google-apps.folder"'),
      order_by = "modifiedTime desc",  # Ordena por fecha de modificación descendente
      n_max = 1  # Toma solamente el primero (el archivo más reciente, aunque en este caso solo es un archivo)
    )
    
    #Se realiza la verificación si se encontró el archivo
    if (nrow(reporte_info) == 0) {
      stop("Error: No se encontró ningún archivo en la carpeta especificada.")
    }
    
    #Se extrae el ID de Google Drive (ID completo para drive_download)
    id_completo_drive <- reporte_info$id[1]
    
    #Obtener la URL de visualización para extraer el ID parcial
    url_completa_view <- reporte_info$drive_resource[[1]]$webViewLink
    
    #Verifica que la URL de visualización sea válida
    if (is.na(url_completa_view)) {
      stop("Error: No se pudo obtener la URL de visualización.")
    }
    
    #Extraer el ID parcial (donde está el archivo)
    id_parcial_extraido <- str_extract(
      string = url_completa_view,
      pattern = "(?<=/d/)(.*?)(?=/view)"
    )
    #Se devuelven ambos IDs
    return(list(
      id_completo = id_completo_drive,
      id_parcial = id_parcial_extraido,
      nombre_archivo_encontrado = reporte_info$name[1]
    ))
  }, error = function(e) {
    cat("Error en obtener los IDs del reporte:", e$message, "\n")
    return(NULL)
  })
}

#' Obtener el ID del reporte de personas en Google Drive
#'
#' Busca en una carpeta de Google Drive el archivo
#' `reporte_personas_completo.parquet`. Si no lo encuentra directamente,
#' también busca dentro de una subcarpeta llamada `cqr`.
#'
#' @param id_carpeta_reporte Character. ID de la carpeta de Google Drive.
#' @return Character: ID del archivo. Se detiene con un error claro si el
#'   archivo no se encuentra.
extraer_id <- function(id_carpeta_reporte) {
  nombre_reporte <- "reporte_personas_completo.parquet"
  message("Buscando el archivo '", nombre_reporte, "' en Google Drive...")

  archivos_carpeta <- drive_ls(path = as_id(id_carpeta_reporte))
  archivo_reporte <- archivos_carpeta[
    archivos_carpeta$name == nombre_reporte,
  ]

  if (nrow(archivo_reporte) == 0) {
    carpeta_cqr <- archivos_carpeta[archivos_carpeta$name == "cqr", ]

    if (nrow(carpeta_cqr) > 0) {
      archivos_cqr <- drive_ls(path = as_id(carpeta_cqr$id[[1]]))
      archivo_reporte <- archivos_cqr[
        archivos_cqr$name == nombre_reporte,
      ]
    }
  }

  if (nrow(archivo_reporte) == 0) {
    stop(
      "No se encontró '", nombre_reporte,
      "' en la carpeta de Drive indicada ni en su subcarpeta 'cqr'. ",
      "Verifica la ubicación, el nombre del archivo y los permisos."
    )
  }

  archivo_reporte$id[[1]]
}

# Genera las carpetas necesarias dentro de *input*, descarga el archivo desde Google Drive y lo almacena en las carpetas creadas
#' Descargar el reporte de personas desde Google Drive a una carpeta con fecha
#'
#' Crea (si no existen) las carpetas
#' `ruta_actual/mes_actual/actualizacion_DD_MM_YYYY` y descarga ahí el
#' archivo de Google Drive indicado por `id_archivo`.
#'
#' @param ruta_actual Ruta base (character) donde se crean las subcarpetas de
#'   mes y de actualización.
#' @param nombre_archivo Nombre (character) con el que se guardará el
#'   archivo descargado, ej. "reporte_personas.xlsx".
#' @param id_archivo Character. ID de Google Drive del archivo a descargar
#'   (ver [obtener_ids_reporte_unico()]).
#' @return Character: la ruta completa donde se guardó el archivo descargado.
descarga_reporte_personas <- function(ruta_actual, nombre_archivo, id_archivo) {
  
  # --- Generación de la ruta dinámica ---
  
  # Obtener la fecha y el mes/año actual
  fecha_actual <- today()
  
  # Generar carpeta
  mes_folder <- format(fecha_actual, "%B_%Y") 
  
  # Crear la ruta completa de la carpeta de destino
  ruta_guardado_folder <- path(ruta_actual, mes_folder)
  
  # Crear la carpeta de mes si no existe
  if (!dir_exists(ruta_guardado_folder)) {
    dir_create(ruta_guardado_folder)
  }
  
  # Crear carpeta con fecha actual
  fecha_actual_carpeta <- format(fecha_actual, "%d_%m_%Y")
  
  actualizacion_mes_folder <- paste0("actualizacion_", fecha_actual_carpeta)
  
  ruta_guardado_actualizacion <- path(ruta_actual, mes_folder, actualizacion_mes_folder)
  
  # Crear la carpeta de actualización si no existe
  if (!dir_exists(ruta_guardado_actualizacion)) {
    dir_create(ruta_guardado_actualizacion)
  }

  # Definir la ruta completa del archivo de destino
  ruta_guardado_archivo <- path(ruta_guardado_actualizacion, nombre_archivo)
  
  # --- Descarga ---
  
  # Descargar el archivo usando la ruta COMPLETA
  drive_download(
    file = as_id(id_archivo),
    path = ruta_guardado_archivo,
    overwrite = TRUE
  )
  
  # Retornamos la ruta donde se guardó el archivo para usarla después
  return(ruta_guardado_archivo)
}

#---------------#
## Paso 2. Función de lectura y limpieza inicial -----
#---------------#

# Objetivo: 1. Leer todas las hojas del Excel. 2. Ordenar las hojas (orden_sheets). 3. Aplicar select y clean_names(). 4. Devolver la lista "comprimido".

#' Leer y clasificar el reporte de personas (pendientes, localizadas, desaparecidas)
#'
#' Lee el archivo `.parquet` del reporte de personas y lo clasifica en tres
#' grupos —`pendientes`, `localizadas` y `desaparecidas`— a partir de las
#' columnas `conidentidad` y `estatus`, en vez de depender de hojas
#' separadas de Excel. También advierte si `fecha_consulta` no corresponde
#' al día de ejecución.
#'
#' Desde la modificación del 18/09/2026, el reporte se descarga como un
#' único archivo `.parquet` (ver [descarga_reporte_personas()]) en lugar de
#' un `.xlsx` con tres hojas, por lo que la clasificación por grupo ya no
#' viene dada por la hoja de origen: se deriva de `conidentidad` (normalizada
#' a minúsculas y sin espacios) y de `estatus` (comparado, sin distinguir
#' mayúsculas/minúsculas, contra "localizada con vida" / "localizada sin
#' vida" para `localizadas`, y "desaparecida" / "no localizada" para
#' `desaparecidas`; el resto con `conidentidad == "false"` cae en
#' `pendientes`).
#'
#' @param reporte_personas Ruta (character) al archivo `.parquet` del
#'   reporte de personas descargado (ver [descarga_reporte_personas()]). Si
#'   la ruta no termina en `.parquet`, la función se detiene con `stop()`.
#' @return Lista de 3 data frames nombrados `pendientes`, `localizadas` y
#'   `desaparecidas`.
lectura_y_limpieza_inicial <- function(reporte_personas) {

  # Modificación 18/09/2026: Ahora el reporte puede venir en formato .parquet, así que read_parquet() 
  comprimido <- if (grepl("\\.parquet$", reporte_personas, ignore.case = TRUE)) {
    # Leer archivo Parquet
    read_parquet(reporte_personas)} else {
    stop("El archivo de reporte debe ser parquet. Se detectó un archivo con extensión diferente: ", tools::file_ext(reporte_personas))
  } 

  # Homogeneizar el nombre de fechahechos
  comprimido <- comprimido |> 
    rename(any_of(c(fechahechos = "FechaHechos")))
  
  # Verificar que la fecha en fecha_consulta de las hojas del archivo correspondan al día de la ejecución del script. En caso de que no correspondan, se descarga el archivo pero con una advertencia para revisar la fecha de consulta.
  fechas_consulta <- sapply(comprimido, function(i) {
    if ("fecha_consulta" %in% names(i)) {
      return(unique(i$fecha_consulta))
    } else {
      return(NA)
    }
  })

  # Fecha de hoy para comparar
  fecha_hoy <- Sys.Date()

  # Comparación de fechas y advertencia
  if (any(!is.na(fechas_consulta) & as.Date(fechas_consulta) != fecha_hoy)) {
    warning("¡Advertencia! La fecha de consulta en el archivo no corresponde al día de hoy. Revisar la fecha_consulta en las hojas del Excel. La fecha detectada fue: ", paste(unique(fechas_consulta), collapse = ", "))
  } else {
    cat("La fecha de consulta en el archivo corresponde al día de hoy. ¡Correcto!\n")
  }

  # En comprimido crear columna llamada 'hoja' que indique si el registro viene de "ACTUALIZACION_PENDIENTE", "LOCALIZADAS", "DESAPARECIDAS"

  # Para esto creemos la columna 'identidad'
  comprimido <- comprimido |> 
    mutate(
      identidad = conidentidad |> str_trim() |> str_to_lower()
    )
  
  localizadas_regex <- regex("^localizada con vida$|^localizada sin vida$", ignore_case = TRUE)
  desaparecidas_regex <- regex("^desaparecida$|^no localizada$", ignore_case = TRUE)

  comprimido <- list(
  pendientes   = comprimido |> filter(identidad == "false" & !str_detect(estatus, localizadas_regex)),
  localizadas  = comprimido |> filter(str_detect(estatus, localizadas_regex)),
  desaparecidas = comprimido |> filter(identidad == "true" & str_detect(estatus, desaparecidas_regex))
)

  return(comprimido)
}

#---------------#
## Paso 3. Función de verificación y duplicación -----
#---------------#

# Objetivo: 1. Ejecutar toda la lógica de indicador_elementos_distintos. 2. Detener la ejecución si la verificación falla (stop()). 3. Aplicar distinct(fub, .keep_all = T). 4. Devolver la lista comprimido limpia.

#' Verificar y eliminar FUBs duplicados con información idéntica
#'
#' Para cada hoja de `comprimido_lista`, identifica los `fub` que aparecen
#' más de una vez y valida que, para cada uno, la información de la víctima
#' (CURP, nombre, apellidos, sexo, entidad de nacimiento concatenados) sea
#' idéntica entre sus filas duplicadas. Si encuentra un `fub` duplicado con
#' información inconsistente, detiene la ejecución con `stop()`; si la
#' validación es exitosa, elimina los duplicados con
#' `distinct(fub, .keep_all = TRUE)`.
#'
#' @param comprimido_lista Lista de data frames (ver
#'   [lectura_y_limpieza_inicial()]), cada uno con columnas `fub`, `estatus`,
#'   `curp_victima` (o `curp_vic`, que se renombra), `nombre_vic`,
#'   `primerapellido_vic`, `segundoapellido_vic`, `sexo` e
#'   `idestadonacimiento_vic`.
#' @return La misma lista de data frames, sin filas duplicadas por `fub`.
#' @note Se detiene con `stop()` si algún `fub` duplicado tiene información
#'   de víctima distinta entre sus filas — eso señalaría que `fub` no es un
#'   identificador único y requeriría revisión manual.
verificacion_y_duplicacion <- function(comprimido_lista) {

  # Homogeneizar la columna de 'curp'. Si en el archivo original viene como 'curp_vic' renombrar a curp_victima:
  if("curp_vic" %in% names(comprimido_lista$pendientes)) {
    comprimido_lista <- lapply(comprimido_lista, function(sheet) {
      sheet |> rename(curp_victima = curp_vic)
    })
  }
  
  # Verificar si los fubs duplicados vienen con información distinta. Nota: idealmente los fubs son indicadores únicos por persona, entonces siempre deberíamos esperar que los fubs duplicados tengan información idéntica entre ellos.
  # Para cada data frame, detecta los fubs que aparecen más de una vez, les crea indicadores y se queda solo con los registros duplicados.
  #Numera y cuenta el número de veces que pertenece cada id
  indicador_elementos_distintos <- comprimido_lista %>%
    map(
      ~ group_by(.x, fub) |> 
        mutate(indicador_rep1 = 1:n(),
               indicador_rep2 = n()) |> 
        #Se queda solo con los id duplicados
        filter(indicador_rep2 > 1) |> 
        select(fub, estatus, curp_victima, indicador_rep1, indicador_rep2, nombre_vic, primerapellido_vic, segundoapellido_vic, sexo, fechanacimiento, idestadonacimiento_vic)
    )
  
  # Creamos una variable que pegue la información de cada fub
  indicador_elementos_distintos <- indicador_elementos_distintos |> 
    map(
      ~ mutate(.x, nombre_concat = paste0(
        curp_victima, " ", nombre_vic, " ", primerapellido_vic, " ", 
        segundoapellido_vic, " ", sexo, " ", idestadonacimiento_vic))
    )
  
  # Agrupar por fub y contar los valores nombre_concat únicos 
  indicador_elementos_distintos <- indicador_elementos_distintos |> 
    map(
      ~ group_by(.x , fub) |> summarise(elementos_unicos = n_distinct(nombre_concat))
    )
  
  # En caso de que ya no haya varios nombre_concat para un mismo fub los valores en ind deben ser de 1
  ind <- lapply(indicador_elementos_distintos, function(sheet) {
    # Usa pull() para convertir esa columna en un vector.
    # Aplica las demás transformaciones (unique, as.numeric).
    # El resultado de la última operación se devuelve automáticamente a 'ind'.
    
    sheet |> 
      dplyr::pull(elementos_unicos) |> # Extrae la columna como vector 
      unique() |> 
      as.numeric()
  })
  
  # Verificamos que para cada fub se tenga un conjunto de curp, nombre completo, sexo, id_estadonacimiento (nombre_concat) único
  resultado_verificacion <- all( # evaluamos que sea TRUE para cada elemento del vector lógico que arroja sapply (a diferencia de lapply, el cual arrojaría una lista)
    sapply(ind, function(valor) {
      all(valor == 1)
    })
  )
  
  if (!resultado_verificacion) {
    print(paste0("¡Error! Los fubs repetidos contienen información inconsistente (elementos_unicos > 1)."))
    stop("Inconsistencia en la identificación de víctimas.")
  } else {
    print(paste0("¡Validación exitosa! Todos los fubs repetidos tienen información de víctima idéntica (elementos_unicos = 1)."))
  }

  # Contar y reportar el total de FUBs duplicados por hoja
  fubs_duplicados <- indicador_elementos_distintos |> 
    map(~ nrow(.x)) 
  
  iwalk(fubs_duplicados, ~ cat("Hoja '", .y, "': ", comma(.x), " FUBs duplicados eliminados.\n", sep = ""))
  
  cat("Total de FUBs duplicados eliminados:", comma(Reduce("+", fubs_duplicados)), "\n")
  
  # Una vez que aseguramos que los fubs tienen información idéntica, podemos eliminar los fubs repetidos de manera segura.
  comprimido <- lapply(comprimido_lista, function(sheet) {
    sheet |> 
      distinct(fub, .keep_all = T)
  })
  
  return(comprimido)
}

#---------------#
## Paso 4. Función de procesamiento de CURPS reconstruidas a partir de RENAPO ---------
#---------------#

# Objetivo: 1. Identificar todos los archivos de CURP en la carpeta cruces/. 
# 2. Aplicar map_dfr() para leer, validar y combinar las 4 bases en un solo data frame reconstruidas. 
# 3. Devolver el data frame reconstruidas final y de duplicado.

#' Consolidar las CURPs reconstruidas por RENAPO en una sola tabla
#'
#' Lee los 4 archivos de `archivos_curp` (CSV o XLSX) desde
#' `ruta_carpeta_cruces`, valida cada CURP obtenida con [es_curp_valida()],
#' se queda solo con las válidas, elimina duplicados por `fub` y cruza el
#' resultado (`reconstruidas`) contra cada hoja de `comprimido_lista` por
#' `fub`.
#'
#' @param comprimido_lista Lista de data frames con columna `fub` (ver
#'   [lectura_y_limpieza_inicial()] / [verificacion_y_duplicacion()]).
#' @param ruta_carpeta_cruces Ruta (character) a la carpeta que contiene los
#'   archivos de CURP reconstruidas. Default: "input/".
#' @return `comprimido_lista`, con una columna adicional `curp_obtenida` en
#'   cada data frame (NA si no hubo cruce por `fub`).
cruzar_y_consolidar_curps <- function(comprimido_lista, ruta_carpeta_cruces = "input/") {
  
  # Definir la lista de archivos de CURP guardadas en la carpeta "input"
  archivos_curp <- c(
    "CURP_act260525.csv",
    "curps_reconstruidas_210625.xlsx",
    "curps_con_resultado_prueba_01072025.xlsx",
    "curps_con_resultado_prueba_050825.xlsx"
  )
  
  # Leer, validar, seleccionar y unir TODAS las bases en una sola tabla 'reconstruidas'
  reconstruidas <- archivos_curp |>
    map_dfr(function(archivo) {
      
      # CONSTRUCCIÓN DE RUTA
      ruta_completa <- paste0(ruta_carpeta_cruces, archivo)
      
      # Lectura condicional (CSV vs. XLSX)
      df <- if (grepl("\\.csv$", archivo)) {
        read.csv(ruta_completa, encoding = "UTF-8")
      } else {
        openxlsx::read.xlsx(ruta_completa)
      }
      
      # Lógica de limpieza y validación
      df |>
        as_tibble() |> 
        select(fub = matches("fub", ignore.case = TRUE),
               curp_obtenida = matches("curp_obtenida|curp", ignore.case = TRUE)) |>
        # Validar la CURP
        mutate(indicadora_curp_valida = ifelse(
          es_curp_valida(curp_obtenida), "valida", "invalida")
        ) |>
        # Filtrar solo las válidas y seleccionar las columnas finales
        filter(indicadora_curp_valida == "valida") |>
        select(fub, curp_obtenida)
    })
  
  # De duplicar la base consolidada
  reconstruidas <- reconstruidas |>
    distinct(fub, .keep_all = TRUE)
  
  # Cruce con los datos principales
  base_final_con_curp <- comprimido_lista |>
    map(~ left_join(.x, reconstruidas, by = "fub"))
  
  return(base_final_con_curp)
}


#' Imputar CURPs reconstruidas y validar que no se pierdan CURPs válidas
#'
#' Para cada hoja de `base_final_con_curp`, evalúa la validez de
#' `curp_victima`; si es inválida y existe `curp_obtenida` (ver
#' [cruzar_y_consolidar_curps()]), la usa para imputar `curp_victima`.
#' Compara el total de CURPs válidas antes y después de la imputación como
#' salvaguarda.
#'
#' @param base_final_con_curp Lista de data frames con columnas
#'   `curp_victima` y `curp_obtenida` (ver [cruzar_y_consolidar_curps()]).
#' @return La misma lista de data frames, con `curp_victima` imputada donde
#'   aplique y una columna adicional `indicadora_curp_valida_final`.
#' @note Se detiene con `stop()` si el número total de CURPs válidas
#'   disminuye tras la imputación (señal de un error de lógica); solo
#'   imprime un mensaje informativo si el número aumenta o se mantiene igual.
imputar_y_validar_curps <- function(base_final_con_curp) {
  
  # Creamos indicadora de curp válida
  base_final_con_curp <- base_final_con_curp |> 
    map(
      ~ mutate(.x, indicadora_curp_valida = ifelse(
        es_curp_valida(curp_victima), "valida", "invalida"
      ))
    )
  
  # Imputar curps reconstuidas
  base_final_con_curp <- base_final_con_curp |> 
    map(
      ~ mutate(.x, curp_victima = case_when(
        indicadora_curp_valida == "valida" ~ curp_victima,
        indicadora_curp_valida == "invalida" & 
          !is.na(curp_obtenida) ~ curp_obtenida,
        TRUE ~ NA
      ))
    )
  
  base_final_con_curp <- base_final_con_curp |> 
    map(
      ~ mutate(.x, indicadora_curp_valida_final  = ifelse(
        es_curp_valida(curp_victima), "valida", "invalida"
      ))
    )
  
  # Esperamos que haya más curps válidas en "indicadora_curp_valida_final" que en "indicadora_curp_valida"
  curps_validas_final <- base_final_con_curp |> 
    map(~ .x |> 
          select(indicadora_curp_valida_final) |> 
          filter(indicadora_curp_valida_final == "valida") |> 
          nrow()) |> 
    unlist() |> 
    sum()
  
  curps_validas_antes <- base_final_con_curp|> 
    map(~ .x |> 
          select(indicadora_curp_valida) |> 
          filter(indicadora_curp_valida == "valida") |> 
          nrow()) |> 
    unlist() |> 
    sum()
  
  if (curps_validas_final > curps_validas_antes) {
    print(paste0("Mejora exitosa: Se validaron ", curps_validas_final - curps_validas_antes, " CURPs adicionales."))
  } else if (curps_validas_final < curps_validas_antes) {
    # Usar 'stop()' para detener la automatización si hay un problema grave
    stop(paste0("¡ERROR! Se perdieron CURPs válidas. Revisar lógica de imputación. Antes: ", curps_validas_antes, ", Después: ", curps_validas_final))
  } else {
    print("La imputación no añadió nuevas CURPs válidas, pero tampoco hubo pérdidas.")
  }
  
  # Lo que devuelve la función imputar_y_validar_curps
  return(base_final_con_curp)
  
}


#' Segmentar la base en "con CURP" y "sin CURP" válida
#'
#' A partir de `base_imputada` (ver [imputar_y_validar_curps()]), separa los
#' registros con `curp_victima` no NA (`base_final_con_curp`) de los que
#' quedaron sin CURP válida, tomando estos últimos de las hojas originales
#' `pendientes` y `desaparecidas` de `comprimido` (excluyendo los FUBs que sí
#' tienen CURP). Verifica que la base "sin CURP" resultante no contenga
#' ninguna CURP válida.
#'
#' @param base_imputada Lista de data frames con `curp_victima` ya imputada
#'   (ver [imputar_y_validar_curps()]).
#' @param comprimido Lista de data frames original y limpia (con los
#'   elementos `pendientes` y `desaparecidas`), usada para no perder columnas
#'   que se hayan descartado durante la imputación.
#' @return Lista con dos elementos: `base_final_con_curp` y
#'   `base_final_sin_curp`, cada uno una lista de data frames.
#' @note Se detiene con `stop()` si `base_final_sin_curp` contiene alguna
#'   CURP válida, lo que indicaría un error en el filtro de segmentación.
segmentar_y_limpiar_bases <- function(base_imputada, comprimido) {
  
  # ------- Base Final CON Curp (Filtrar los que SÍ tienen CURP) ----
  
  base_con_curp <- base_imputada |>
    # Nos quedamos solo con los registros que tienen una CURP imputada o validada
    map(~ filter(.x, !is.na(curp_victima)))
  
  # Generamos un vector único de FUBs que ya tienen una CURP
  fubs_con_curp <- base_con_curp |>
    map(~ pull(.x , fub)) |>
    unlist() |>
    unique()
  
  # -------- Base Final SIN Curp (Filtro Anti-FUB) ------------
  
  # Usamos la lista ORIGINAL LIMPIA (comprimido_original) para no perder columnas
  # que se pudieron haber perdido en la imputación.
  
  # Creamos una base temporal con las hojas que deberían contener a los 'sin curp'
  comprimido_solo_desaparecidos <- comprimido[c("pendientes", "desaparecidas")]
  
  # Quitar los FUBs que ya se encontraron en la base 'CON CURP'
  base_sin_curp <- comprimido_solo_desaparecidos |>
    map(
      ~ filter(.x , !fub %in% fubs_con_curp)
    )
  
  # ------- Verificación y Limpieza Final -------
  
  # Verificación: no debe quedar ninguna CURP válida
  conteo_de_curps_sin_curp <- base_sin_curp |>
    map_dfr(
      ~ .x |>
        mutate(indicadora_curp_valida_final = ifelse(es_curp_valida(curp_victima), "valida", "invalida")) |>
        count(indicadora_curp_valida_final),
      .id = "fuente_df"
    )
  
  if (all(conteo_de_curps_sin_curp$indicadora_curp_valida_final == "invalida")) {
    print("Validación de segmentación: La base SIN CURP solo contiene registros sin CURP válida. ¡Correcto!")
  } else {
    stop("¡ERROR de segmentación! Se detectaron CURPs válidas en la base SIN CURP. Revisar filtro.")
  }
  
  # ----------- Devolver las Bases Finales ----------
  return(list(
    base_final_con_curp = base_con_curp,
    base_final_sin_curp = base_sin_curp
  ))
}

#---------------#
## Paso 5. Función de verificación ------
#---------------#

# Objetivo: 1. verificamos que tengamos fubs únicos en ambas bases de "bases_segmentadas" 
# 2. verificamos que NO hay curps únicos en base_final_con_curp.

#' Verificar unicidad de FUBs y no unicidad de CURPs en las bases segmentadas
#'
#' Comprueba que `base_final_sin_curp` y `base_final_con_curp` tengan un
#' `fub` único por fila, y que `base_final_con_curp` NO tenga `curp_victima`
#' totalmente única (se espera que algunas CURPs se repitan entre FUBs
#' distintos, p. ej. errores de captura). Imprime el resultado con `print()`.
#'
#' @param bases_segmentadas Lista con los elementos `base_final_con_curp` y
#'   `base_final_sin_curp`, tal como la regresa [segmentar_y_limpiar_bases()].
#' @return `NULL` invisible; su efecto es imprimir en consola si la
#'   verificación de unicidad fue correcta o no.
verificacion_fubs_curps <- function(bases_segmentadas) {
  
  # ----- base_final_sin_curp ------
  # Verificamos que todos los fubs de base_final_sin_curp sean únicos
  verificacion_fub_unicos <- bases_segmentadas$base_final_sin_curp |>
    map_lgl(
      ~ {
        # Obtener el número de filas (registros)
        num_filas <- nrow(.x)
        
        # Obtener el número de valores únicos en la columna 'fub'
        num_fubs_distintos <- n_distinct(.x$fub) # o length(unique(.x$fub))
        
        # Comparar: Son únicos si el número de filas es igual al número de FUBs distintos
        num_filas == num_fubs_distintos
      }
    )
  
  # Realizamos una verificación global (que sea TRUE para todos los DF's):
  verificacion_global_1 <- all(verificacion_fub_unicos)
  
  # ----- base_final_con_curp ------
  # Verificamos que la base_final_con_curp tiene fubs únicos pero no curps únicos
  verificacion_fub_unicos <- bases_segmentadas$base_final_con_curp |> 
    map_lgl(
      ~ {
        # Número de filas
        n_row <- nrow(.x)
        
        # Número de valores únicos de la columna 'fub'
        num_fubs_unicos <- n_distinct(.x$fub)
        
        # Comparar ambos valores
        n_row == num_fubs_unicos
      }
    )
  
  # Realizamos una verificación global (que sea TRUE para todos los DF's):
  verificacion_global_2 <- all(verificacion_fub_unicos)
  
  # Sin embargo, para base_final_con_curp no tenemos curps únicos
  verificacion_curps_unicos <- bases_segmentadas$base_final_con_curp |> 
    map_lgl(
      ~ {
        n_row <- nrow(.x)
        
        n_curps_unicos <- n_distinct(.x$curp_victima)
        
        # Comparamos ambos valores
        n_row == n_curps_unicos
      }
    )
  
  # Realizamos una verificación global (que sea TRUE para todos los DF's):
  verificacion_global_3 <- all(verificacion_curps_unicos)
  
  if (verificacion_global_1 == TRUE &
      verificacion_global_2 == TRUE &
      verificacion_global_3 == FALSE) { # Esperamos que los CURPs NO sean totalmente únicos
    
    print("Verificación de unicidad CORRECTA.")
    print("* FUBs en ambas bases: Únicos (OK)")
    print("* CURPs en base_final_con_curp: NO totalmente Únicos (OK)")
    
  } else {
    # Proporcionar un mensaje más específico en caso de fallo
    print("Algo salió mal en la verificación de unicidad. Favor de corregir.")
    print(paste0("FUBs sin CURP (esperado TRUE): ", verificacion_global_1))
    print(paste0("FUBs con CURP (esperado TRUE): ", verificacion_global_2))
    print(paste0("CURPs con CURP (esperado FALSE): ", verificacion_global_3))
  }
  
}

#---------------#
## Paso 6. Función de creación de nuevo documento .parquet ya con los cambios hechos -----
#---------------#

#' Ensamblar y guardar el archivo .parquet final con las 3 hojas procesadas
#'
#' Elimina la columna auxiliar `curp_obtenida` de `base_final_con_curp`,
#' unifica los tipos de columna `ren_*` en `base_final_sin_curp`, y arma una
#' sola tabla larga apilando tres bloques: ACTUALIZACION_PENDIENTE (unión de
#' todas las hojas de `base_final_sin_curp`), DESAPARECIDAS
#' (`base_final_con_curp$desaparecidas`) y LOCALIZADAS
#' (`comprimido_limpio$localizadas`, la lista original sin segmentar). Una
#' columna `hoja` identifica el origen de cada fila y las columnas que no
#' coinciden entre bloques quedan como `NA` (vía [dplyr::bind_rows()]). Guarda
#' el archivo en
#' `RNPDNO/output/bases_procesadas_rnpdno/<mes>/actualizacion_<fecha>/base_final_reporte_personas_<fecha>.parquet`,
#' creando las carpetas necesarias.
#'
#' @param bases_segmentadas Lista con `base_final_con_curp` y
#'   `base_final_sin_curp` (ver [segmentar_y_limpiar_bases()]).
#' @param comprimido_limpio Lista de data frames original y limpia (ver
#'   [verificacion_y_duplicacion()]), de la cual se usa el elemento
#'   `localizadas` sin modificar.
#' @return Character: la ruta completa del archivo .parquet guardado.
crear_parquet <- function(bases_segmentadas, comprimido_limpio) {
  # ... Lógica interna de eliminación de columnas innecesarias ...

  # Eliminar columnas innecesarias de curps de la base final con curp
  bases_segmentadas$base_final_con_curp <- bases_segmentadas$base_final_con_curp |>
    map(
      ~ .x |>
        select(-c(curp_obtenida)) |> 
        mutate(ren_curp = as.character(ren_curp),
               ren_nombres = as.character(ren_nombres),
               ren_apellido1 = as.character(ren_apellido1),
               ren_apellido2 = as.character(ren_apellido2),
               ren_sexo = as.character(ren_sexo),
               ren_fechnac = as.Date(ren_fechnac, format = "%d/%m/%Y"),
               ren_nacionalidad = as.character(ren_nacionalidad),
               ren_cveentidadnac = as.character(ren_cveentidadnac),
               ren_statuscurp = as.character(ren_statuscurp),
               ren_fecha = as.Date(ren_fecha, format = "%Y-%m-%d")
        )
    )

  # PENDIENTES (Base SIN CURP)
  # Combinamos todos los data frames dentro de base_final_sin_curp

  # Forzamos mismo formato en "ren_curp"
  base_sin_curp_preparada <- bases_segmentadas$base_final_sin_curp |>
    map(
      ~ .x |>
        mutate(ren_curp = as.character(ren_curp),
               ren_nombres = as.character(ren_nombres),
               ren_apellido1 = as.character(ren_apellido1),
               ren_apellido2 = as.character(ren_apellido2),
               ren_sexo = as.character(ren_sexo),
               ren_fechnac = as.Date(ren_fechnac, format = "%d/%m/%Y"),
               ren_nacionalidad = as.character(ren_nacionalidad),
               ren_cveentidadnac = as.character(ren_cveentidadnac),
               ren_statuscurp = as.character(ren_statuscurp),
               ren_fecha = as.Date(ren_fecha, format = "%Y-%m-%d")
        )
    )

  base_sin_curp_unida <- base_sin_curp_preparada |>
    map_dfr(.f = identity)

  # DESAPARECIDAS (Base CON CURP, solo los desaparecidos)
  base_desaparecidas <- bases_segmentadas$base_final_con_curp$desaparecidas

  # LOCALIZADAS (Se mantiene la lista original limpia, NO la segmentada)
  base_localizadas <- comprimido_limpio$localizadas |>
    mutate(ren_curp = as.character(ren_curp),
           ren_nombres = as.character(ren_nombres),
           ren_apellido1 = as.character(ren_apellido1),
           ren_apellido2 = as.character(ren_apellido2),
           ren_sexo = as.character(ren_sexo),
           ren_fechnac = as.Date(ren_fechnac, format = "%d/%m/%Y"),
           ren_nacionalidad = as.character(ren_nacionalidad),
           ren_cveentidadnac = as.character(ren_cveentidadnac),
           ren_statuscurp = as.character(ren_statuscurp),
           ren_fecha = as.Date(ren_fecha, format = "%Y-%m-%d")
    )

  # Guardar el archivo
  fecha_actual <- today()
  fecha_workbook <- format(fecha_actual, "%d%m%Y")
  mes_folder <- format(fecha_actual, "%B_%Y")

  # Crear carpeta de actualización si no existe
  carpeta <- here::here("RNPDNO","output", "bases_procesadas_rnpdno", mes_folder, paste0("actualizacion_", fecha_workbook))

  if (!dir_exists(carpeta)) {
    dir_create(carpeta, recurse = TRUE)

    if (dir_exists(carpeta)) {
      cat("Carpeta creada exitosamente: ", carpeta, "\n")
    } else {
      stop("Error al crear la carpeta: ", carpeta)
    }
  } else {
    cat("La carpeta ya existe: ", carpeta, "\n")
  }

  # Se apilan las 3 hojas en una sola tabla larga (columna 'hoja' indica el
  # origen; dplyr::bind_rows() rellena con NA las columnas que no coincidan
  # entre las 3 hojas).
  base_final_larga <- bind_rows(
    list(
      ACTUALIZACION_PENDIENTE = base_sin_curp_unida,
      DESAPARECIDAS = base_desaparecidas,
      LOCALIZADAS = base_localizadas
    ),
    .id = "hoja"
  )

  ruta_archivo_parquet <- paste0(carpeta, "/base_final_reporte_personas_", fecha_workbook, ".parquet")

  write_parquet(base_final_larga, ruta_archivo_parquet)

  cat("Parquet guardado exitosamente: ", ruta_archivo_parquet, "\n")

  return(ruta_archivo_parquet)
}

#---------------#
## Paso 7. Función que consolida todas las funciones anteriores en un único flujo -----
#---------------#

#' Orquestar la descarga, limpieza, cruce y guardado del reporte de personas
#'
#' Ejecuta en secuencia los pasos 1 a 7 de la descarga/limpieza de BANCI-RNPDNO:
#' descarga desde Drive ([descarga_reporte_personas()]), limpieza de
#' actualizaciones viejas ([limpiar_actualizaciones_viejas_rnpdno()]), lectura de
#' hojas ([lectura_y_limpieza_inicial()]), deduplicación de FUBs
#' ([verificacion_y_duplicacion()]), cruce e imputación de CURPs
#' ([cruzar_y_consolidar_curps()] + [imputar_y_validar_curps()]),
#' segmentación ([segmentar_y_limpiar_bases()]), verificación de unicidad
#' ([verificacion_fubs_curps()]) y guardado del workbook final
#' ([crear_parquet()]). Cada paso está envuelto en `tryCatch()` /
#' `withCallingHandlers()` para registrar advertencias y errores con
#' `message()` sin detener abruptamente el flujo completo.
#'
#' @param id_archivo_reporte_personas Character. ID de Google Drive del
#'   archivo de reporte de personas a descargar (ver [extraer_id()] /
#'   [obtener_ids_reporte_unico()]).
#' @param ruta_carpeta_cruces Ruta (character) a la carpeta con los archivos
#'   de CURP reconstruidas, usada por [cruzar_y_consolidar_curps()]. Default:
#'   "input/bases_descargadas_rnpdno/".
#' @param ruta_reporte_local Character o NULL. Ruta a un
#'   `reporte_personas_completo.parquet` descargado manualmente. Si se
#'   proporciona, se omite la descarga desde Google Drive y la limpieza de
#'   carpetas de actualizaciones viejas, y el resto de los pasos se ejecuta
#'   sobre este archivo. Default: NULL (descarga desde Drive).
#' @return Character: la ruta del archivo .parquet final guardado (ver
#'   [crear_parquet()]). Se detiene con `stop()` si falla el paso 1
#'   (descarga o archivo local inexistente); los demás pasos capturan sus
#'   propios errores y continúan con `NULL` en la variable correspondiente si
#'   fallan.
automatizar_base_final_rnpdno <- function(id_archivo_reporte_personas = NULL,
                                          ruta_carpeta_cruces = "input/bases_descargadas_rnpdno/",
                                          ruta_reporte_local = NULL) {
  # 1. ENTRADA: Descarga del archivo fuente (Reporte Personas)

  # Si se proporcionó un archivo descargado manualmente, se usa ese y se omite
  # la descarga. También se omite la limpieza de carpetas viejas: el archivo
  # puede estar fuera de la estructura <mes>/actualizacion_<fecha>, y en ese
  # caso la limpieza podría borrar carpetas que no corresponden.
  if (!is.null(ruta_reporte_local)) {
    if (!file.exists(ruta_reporte_local)) {
      stop("[Bot] No se encontró el archivo local: ", ruta_reporte_local)
    }
    message("Paso 1: Se omite la descarga. Usando archivo local: ", ruta_reporte_local, "\n")
    reporte_personas <- ruta_reporte_local
  } else {
  # Se usa la ruta_actual definida en el script original
  message("Paso 1: Descargando archivo de personas desde Google Drive...\n")

  reporte_personas <- tryCatch(
    { 
      withCallingHandlers(
        descarga_reporte_personas(
          ruta_actual = path("input/bases_descargadas_rnpdno/"),
          nombre_archivo = "reporte_personas_completo.parquet",
          id_archivo = id_archivo_reporte_personas),
        warning = function(w) {
          message("[Warning Paso 1] ", conditionMessage(w), "\n")

          }
        )
      },
    error = function(e) {
      message("[Error Paso 1] Error al descargar el archivo: ",
          conditionMessage(e), "\n")
      return(NULL)
      }
    )
  
  if (is.null(reporte_personas)) stop("[Bot] Falló el paso 1. Abortando...")
  
  # Paso intemedio: limpiar carpeta de archivos de entrada
  message("Limpiando carpeta de archivos para conservar solo el archivo de RNPDNO más reciente, más próximo a la mitad del mes y más cercano al final del mes\n")


  tryCatch(
  {
    withCallingHandlers(
      limpiar_actualizaciones_viejas_rnpdno(
        ruta_guardado_folder = fs::path_dir(fs::path_dir(reporte_personas)),  
        mantener_ultimas = 3
      ),
      warning = function(s) {
        message("[Warning Paso de Limpieza de Carpeta] ", conditionMessage(s), "\n")
        invokeRestart("muffleWarning")
      }
    )
  },
  error = function(e) {
    message("[Error Paso de Limpieza de Carpeta] Error al eliminar y limpiar archivos:\n",
        conditionMessage(e), "\n")
  }
  )
  }

  # reporte_personas sigue intacto aquí, con su ruta_csv, ruta_zip, etc.
  
  # 2. LECTURA: Lectura y limpieza inicial (Comprimido)
  message("Paso 2: Leyendo y limpiando hojas de cálculo.\n")
  comprimido <- tryCatch(
    {
      withCallingHandlers(
        lectura_y_limpieza_inicial(
          reporte_personas = reporte_personas),
        warning = function(w) {
          message("[Warning Paso 2] ", conditionMessage(w), "\n")

          }
        )
      },
    error = function(e) {
      message("[Error Paso 2] Error al leer y limpiar hojas:\n",
          conditionMessage(e), "\n")
      return(NULL)
      }
    )
    
  # 3. LIMPIEZA: Verificación de inconsistencia de FUBs duplicados
  message("Paso 3: Verificando y eliminando FUBs duplicados con información idéntica.\n")
  comprimido_limpio <- tryCatch(
    {
      withCallingHandlers(
        verificacion_y_duplicacion(comprimido_lista = comprimido),
        warning = function(w) {
          message("[Warning Paso 3] ", conditionMessage(w), "\n")
          })
      },
    error = function(e) {
      message("[Error Paso 3] Error al verificar y eliminando FUBs duplicados: ",
          conditionMessage(e), "\n")
      return(NULL)
      }
    )
      
  # 4. CRUCE/IMPUTACIÓN: Cruce con CURPs reconstruidas de RENAPO
  message("Paso 4: Cruzando con CURPs reconstruidas.\n")
  base_final_con_curp_cruzada <- tryCatch(
    {
      withCallingHandlers(
        cruzar_y_consolidar_curps(
          comprimido_lista = comprimido_limpio,
          ruta_carpeta_cruces = "input/"),
        warning = function(w) {
          message("[Warning Paso 4] ", conditionMessage(w), "\n")
          }
        )
      },
    error = function(e) {
      message("[Error Paso 4] Error al cruzar con CURPs reconstruidas: ",
          conditionMessage(e), "\n")
      return(NULL)
      }
    )
  message("Paso 4.1: Imputando CURPs reconstruidas a la base original.\n")
  base_imputada <- tryCatch(
    { 
      withCallingHandlers(
        imputar_y_validar_curps(base_final_con_curp = base_final_con_curp_cruzada),
        warning = function(w) {
          message("[Warning Paso 4.1] ", conditionMessage(w), "\n")
          }
        )
      },
    error = function(e) {
      message("[Error Paso 4] Error al imputar CURPs reconstruidas a la base original.: ",
          conditionMessage(e), "\n")
      return(NULL)
      }
    )
  # 5. SEGMENTACIÓN: Segmentar por "Con CURP" y "Sin CURP"
  message("Paso 5: Segmentando la base en registros con y sin CURP válida.\n")
  bases_segmentadas <- tryCatch(
    { 
      withCallingHandlers(
        segmentar_y_limpiar_bases(
          base_imputada = base_imputada,
          comprimido = comprimido_limpio), # Se utiliza el comprimido 
    #limpio para el filtro SIN CURP
    warning = function(w) {
      message("[Warning Paso 5] ", conditionMessage(w), "\n")
      }
    )
      },
    error = function(e) {
      message("[Error Paso 5] Error al segmentar la base en registros con y sin CURP válida.: ",
          conditionMessage(e), "\n")
      return(NULL)
      }
    )

  # 6. VERIFICACIÓN FINAL: Unicidad de FUBs y CURPs
  message("Paso 6: Realizando verificación de unicidad final.\n")
  verifica <- tryCatch(
    {
      withCallingHandlers(
        verificacion_fubs_curps(bases_segmentadas = bases_segmentadas),
        warning = function(w) {
          message("[Warning Paso 6] ", conditionMessage(w), "\n")
          }
        )
      },
    error = function(e) {
      message("[Error Paso 6] Error al realizar la verificación de unicidad final,: ",
          conditionMessage(e), "\n")
      return(NULL)
      }
    )

  # 7. SALIDA: Creación del nuevo archivo Parquet (.parquet)
  # La función crear_parquet incluye la limpieza de columnas innecesarias 
  # y la unión de las bases para el archivo final. (la variable 'comprimido' 
  # aún contiene las bases originales limpias, necesarias para la hoja 
  # LOCALIZADAS en tu función)
  
  # Nota: usar 'comprimido_limpio' que es el resultado del paso 3.
  message("Paso 7: Creando y guardando el nuevo documento de reporte de personas.\n")
  base_final_guardada <- tryCatch(
    {
      withCallingHandlers(
        crear_parquet(bases_segmentadas = bases_segmentadas,
                       comprimido_limpio = comprimido_limpio),
      
  # Devuelve el path del archivo creado para confirmación
        warning = function(w) {
    message("[Warning Paso 7] ", conditionMessage(w), "\n")
          }
        )
      },
  error = function(e) {
    message("[Error Paso 7] Error al crear y guardar el nuevo documento de reporte de personas.: \n",
        conditionMessage(e), "\n")
    return(NULL)
    }
  )
  message("¡Proceso de automatización finalizado con éxito! \n")
        return(base_final_guardada)

}

# ————————————————————————————————————————————————————————— #
# Catálogo de regex válidos de carpetas de investigación según entidad federativa ------
# ————————————————————————————————————————————————————————— #

# Assumption: Tanto las comisiones de búsqueda locales como las fiscalías locales deben regirse bajo los mismos parámetros de nomenclatura.
# Localidades de Baja California Sur
nomenclaturas_bcs <- c("LPZ", "TS", "PLN", "LBR", "SGO", "SJC", "CSL", "CST",
                       "INS", "SCL", "LOR", "MGE", "SRL", "GNO", "VIZ", "BT")

# Prefijos para Coahuila
prefijo_coah <- "(?:c\\.?i\\.?|a\\.?p\\.?p\\.?)"   # CI o APP, con puntos opcionales

# Catálogo de nomenclaturas de agencias y unidades de la Fiscalía de Oaxaca (versión completa)
# Fuente: nomenclatura_todos_oaxaca_05102026.xlsx (131 registros)
catalogo_nomenclatura_oaxaca_todos <- tribble(
  ~nomenclatura, ~agencia_unidad,
  "UEDF",            "UNIDAD ESPECIAL EN DESAPARICION FORZADA",
  "SAVJRSC",         "MESA DE PERSONAS DESAPARECIDAS",
  "ADNOL",           "UNIDAD DE ATENCION A PERSONAS NO LOCALIZADAS",
  "RDNOL",           "UNIDAD DE ATENCION A PERSONAS NO LOCALIZADAS",
  "DNOL",            "UNIDAD DE ATENCION A PERSONAS NO LOCALIZADAS",
  "ACATLAN",         "ACATLAN DE PEREZ FIGUEROA",
  "AYUTLA",          "SAN PEDRO SAN PABLO AYUTLA MIXES",
  "FIXTLAN",         "FISCALIA DE IXTLAN DE JUAREZ",
  "FTFM",            "FISCALIA DE TEOTITLAN DE FLORES MAGON",
  "FCUICA",          "FISCALIA DE SAN JUAN BAUTISTA CUICATLAN",
  "FVA",             "FISCALIA DE VILLA ALTA",
  "FZAC",            "FISCALIA DE ZACATEPEC MIXE",
  "VGCR",            "VICEFISCALIA GENERAL DE CONTROL REGIONAL",
  "FAYUTLA",         "FISCALIA DE AYUTLA, MIXE",
  "FHJ",             "FISCALIA DE HUAUTLA DE JIMENEZ",
  "CATL",            "COORDINACION DE APOYO TECNICO Y LITIGACION",
  "CHAHUITES",       "CHAHUITES",
  "CODDI-OCOTLAN",   "OCOTLAN DE MORELOS - CODDI",
  "CODDI-TUXTEPEC",  "SAN JUAN BAUTISTA TUXTEPEC - CODDI",
  "CODDI-ZAACHILA",  "VILLA DE ZAACHILA - CODDI",
  "COIXTLAHUACA",    "SAN JUAN BAUTISTA COIXTLAHUACA",
  "COSOLAPA",        "SAN JOSE COSOLAPA",
  "CUICATLAN",       "SAN JUAN BAUTISTA CUICATLAN",
  "FRG",             "FISCALIA DE RIO GRANDE",
  "SPP",             "SAN PEDRO POCHUTLA",
  "FPE",             "FISCALIA DE PUERTO ESCONDIDO",
  "FSPN",            "FISCALIA DE SANTIAGO PINOTEPA NACIONAL",
  "PN",              "PINOTEPA NACIONAL",
  "FSJ.",            "FISCALIA DE SANTIAGO JAMITELPEC",
  "PE",              "PUERTO ESCONDIDO",
  "FSBCH",           "FISCALIA DE SANTA CRUZ HUATULCO",
  "FSPP",            "FISCALIA DE SAN PEDRO POCHUTLA",
  "DATS",            "DIRECCION DE ASUNTOS DE TRASCENDENCIA SOCIAL",
  "EJUTLA",          "EJUTLA DE CRESPO",
  "ETLA",            "ETLA",
  "FADO",            "FISCALIA ESPECIALIZADA EN JUSTICIA PARA ADOLESCENTES",
  "FADO-HUAJUAPAN",  "HUAJUAPAN DE LEON - FADO",
  "FADO-JUCHITAN",   "JUCHITAN DE ZARAGOZA - FADO",
  "FADO-PUERTO",     "PUERTO ESCONDIDO - FADO",
  "FAMI-IXTEPEC",    "IXTEPEC - FAMI",
  "FACAT",           "FISCALIA DE ACATLAN DE PEREZ FIGUEROA",
  "FTDAI",           "FISCALIA DE ALTO IMPACTO CUENCA",
  "FTUXT",           "FISCALIA DE TRAMITE TUXTEPEC",
  "FTUXM",           "FISCALIA DE DELITOS CONTRA LA MUJER POR RAZON DE GENERO CUENCA",
  "FMLOM",           "FISCALIA DE MARIA LOMBARDO DEL CASO",
  "FLOMA",           "FISCALIA DE LOMA BONITA CUENCA",
  "FAMI-MATIAS",     "MATIAS ROMERO AVENDANO - FAMI",
  "FAMI-YAUTEPEC",   "SAN CARLOS YAUTEPEC - FAMI",
  "FDPE",            "FISCALIA CONTRA LA DESAPARICION DE PERSONAS",
  "FMUJ-TLAXIACO",   "HEROICA CIUDAD DE TLAXIACO - FMUJ",
  "HUAJUAPAN",       "HUAJUAPAN DE LEON",
  "HUATULCO",        "SANTA CRUZ HUATULCO",
  "HUAUTLA",         "HUAUTLA DE JIMENEZ",
  "IXTEPEC",         "IXTEPEC",
  "ZN",              "SANTO DOMINGO ZANATEPEC",
  "JU",              "JUCHITAN DE ZARAGOZA",
  "TH",              "TEHUANTEPEC",
  "MR",              "MATIAS ROMERO",
  "CH.",             "FISCALIA MIGRANTE CHAHUITES",
  "SC.",             "SALINA CRUZ",
  "IXTLAN",          "IXTLAN DE JUAREZ",
  "JAMILTEPEC",      "SANTIAGO JAMITELPEC",
  "JUCHITAN",        "JUCHITAN DE ZARAGOZA",
  "JUQUILA",         "SANTA CATARINA JUQUILA",
  "JUXTLAHUACA",     "SANTIAGO JUXTLAHUACA",
  "LOMA",            "LOMA BONITA",
  "LOMBARDO",        "MARIA LOMBARDO DE CASO",
  "MATIAS",          "MATIAS ROMERO AVENDANO",
  "MIAHUATLAN",      "MIAHUATLAN DE PORFIRIO DIAZ",
  "NOCHIXTLAN",      "ASUNCION NOCHIXTLAN",
  "OAXACA",          "OAXACA DE JUAREZ",
  "OCOTLAN",         "OCOTLAN DE MORELOS",
  "HL",              "HUAJUAPAN DE LEON",
  "TX",              "FISCALIA DE TLAXIACO",
  "FSJ",             "FISCALIA DE SANTIAGO JUXTLAHUACA",
  "PG",              "PUTLA DE GUERRERO",
  "DNOLMIXTECA-TX",  "DNOL TLAXIACO",
  "PINOTEPA",        "SANTIAGO PINOTEPA NACIONAL",
  "POCHUTLA",        "SAN PEDRO POCHUTLA",
  "PUERTO",          "PUERTO ESCONDIDO",
  "PUTLA",           "PUTLA DE VILLA DE GUERRERO",
  "RIO",             "RIO GRANDE",
  "SALINA",          "SALINA CRUZ",
  "SILACAYOAPAM",    "SILACAYOAPAM",
  "SOLA",            "SOLA DE VEGA",
  "SOYALTEPEC",      "SAN MIGUEL SOYALTEPEC",
  "TEHUANTEPEC",     "SANTO DOMINGO TEHUANTEPEC",
  "FOM",             "FISCALIA OCOTLAN DE MORELOS",
  "ETLA",            "ETLA.",
  "SC",              "SECTOR CENTRAL",
  "CR",              "CRUZ ROJA",
  "FEC",             "FISCALIA EJUTLA DE CRESPO",
  "ZIMATLAN",        "ZIMATLAN DE ALVAREZ...",
  "SAVJ",            "SUBPROC ATN A VIC JR Y SC",
  "FZIM",            "FISCALIA ZIMATLAN DE ALVAREZ",
  "AYUTLA",          "SAN PEDRO Y SAN PABLO AYUTLA.",
  "EJUTLA",          "EJUTLA DE CRESPO.",
  "FTM",             "FISCALIA TLACOLULA DE MATAMOROS",
  "OCOTLAN",         "OCOTLAN DE MORELOS.",
  "PME",             "POLICIA MINISTERIAL DEL E",
  "OAXACA",          "OAXACA ZONA CENTRO.",
  "FETLA",           "FISCALIA ETLA",
  "ZAACHILA",        "ZAACHILA.",
  "CH",              "CENTRO HISTORICO",
  "FZAA",            "FISCALIA ZAACHILA",
  "TLACOLULA",       "TLACOLULA.",
  "TEOTITLAN",       "TEOTITLAN DE FLORES MAGON",
  "TEPOSCOLULA",     "SAN PEDRO Y SAN PABLO TEPOSCOLULA",
  "TLACOLULA",       "TLACOLULA DE MATAMOROS",
  "TLAXIACO",        "HEROICA CIUDAD DE TLAXIACO",
  "TUXTEPEC",        "SAN JUAN BAUTISTA TUXTEPEC",
  "UDNA",            "UNIDAD DE DELITOS CONTRA NINOS, NINAS Y ADOLESCENTES",
  "UECS",            "UNIDAD ESPECIALIZADA EN EL COMBATE AL SECUESTRO Y EXTORSION",
  "UEIH",            "UNIDAD ESPECIALIZADA EN LA INVESTIGACION DE HOMICIDIOS",
  "UELE",            "UNIDAD ESPECIALIZADA PARA LA ATENCION DE DELITOS COMETIDOS EN CONTRA DE LA LIBERTAD DE EXPRESION",
  "UNNA",            "UNIDAD OPERATIVA ESPECIALIZADA PARA NINAS, NINOS Y ADOLESCENTES VICTIMAS DEL DELITO",
  "DS",              "DELITOS SEXUALES",
  "UNOL",            "UNIDAD DE BUSQUEDA DE PERSONAS NO LOCALIZADAS",
  "AM.",             "ATENCION A MENORESS",
  "VALLE-NACIONAL",  "SAN JUAN BAUTISTA VALLE NACIONAL",
  "VILLA",           "SAN IDELFONSO VILLA ALTA",
  "YAUTEPEC",        "SAN CARLOS YAUTEPEC",
  "FCDO",            "FISCALIA DE COMBATE A LA DELINCUENCIA ORGANIZADA",
  "FEDAI",           "FISCALIA ESPECIALIZADA PARA LA ATENCION A DELITOS DE ALTO IMPACTO",
  "SADAI",           "SUBPROC PARA LA ATENCION DE DELITOS DE ALTO IMPACTO",
  "ZAACHILA",        "VILLA DE ZAACHILA",
  "FEADAI",          "FISCALIA ESPECIALIZADA PARA LA ATENCION A DELITOS DE ALTO IMPACTO (6 SIGLAS)",
  "ZACATEPEC",       "SANTIAGO ZACATEPEC MIXES",
  "ZANATEPEC",       "SANTO DOMINGO ZANATEPEC",
  "FIDTS",           "FISCALIA DE INVESTIGACION EN DELITOS DE TRASCENDENCIA SOCIAL",
  "ZIMATLAN",        "ZIMATLAN DE ALVAREZ"
)

catalogo_regex_ci_por_entidad <- c(
  "Aguascalientes" = "^(?:CI|CH|ACTC)[-/][A-Za-z]{3}[-/]\\d{5}[-/](0[1-9]|1[0-2])[-/]\\d{2}$", 
  "Baja California" = "^(?i)(?:[a-z]+[-/]?)?\\d(?:[-/]?\\d{2})(?:[-/]?\\d{3})(?:[-/]?\\d{4})(?:[-/]?\\d{5})$",

  "Baja California Sur" = str_c("^(?i)(?:", str_c(nomenclaturas_bcs, collapse = "|"), ")",  # nomenclatura
  "(?:[-/]?[1-9]\\d*)",                                         # número
  "(?:[-/]?[a-z0-9]+)",                                         # alfanumérico
  "(?:[-/]?(?:nuc|\\d{4}))$"                                    # NUC o año
  ),
  "Chiapas" = "^(?i)\\d{4}(?:[-/]?\\d{3})(?:[-/]?\\d{4})(?:[-/]?\\d{4,5})$", # Añadimos una relajación para el último segmento (que corresponde al año), ya que puede haber un typo (ej. "20256" en lugar de "2025")
  "Chihuahua" = "^(?i)\\d{2}(?:[-/]?\\d{4})(?:[-/]?\\d{7})$",
  "Ciudad de México" = "^(?i)(?:ci|ae)[-/](?:e[-/])?f[a-z0-9]+[-/][a-z0-9]+(?:[/-][a-z0-9]+)*[-/]ui[-/]?\\d+(?:\\s)?(?:[-/]?(?:s|c)[-/]d)[-/]\\d{5}[-/](0[1-9]|1[0-2])[-/]\\d{4}$",

  "Campeche"  = "^(?i)(?:ci|ac)(?:[-/]?\\d{1,3})(?:[-/]?\\d{4})(?:[-/]?[1-9]\\d*)$",
  "Coahuila" = str_c(
    "^(?i)", prefijo_coah, "(?:[-/]?", prefijo_coah, ")?",  # CI, APP o ambos
    "[-/]\\d+",                                             # número
    "[-/](?:\\d{4}|[a-z]+)",                                # año o texto alfabético
    "(?:[-/](?:ulpnl|atpd)[-/]\\d{4})?$"                    # extensión opcional
    ),
  "Colima" = "^(?i)nsjp/[a-z]{3}/(?:ci|ch)/[a-z0-9]{1,50}[ /][0-9]{1,3}/\\d{4}$", # Diagonales como separadores; antes del número se permite espacio o diagonal
  "Durango" = "^(?i)c\\.?(?:d\\.?)?i\\.?/fge/r[0-9]{1,2}(?:/[a-z]{3})?/\\d+/\\d{4}$",
  "Guanajuato" = "^(?i)\\d+(?:[-/]?\\d{4})$",
  "Guerrero" = "^(?i)(?:\\d{14}(0[1-9]|[12]\\d|3[01])(0[1-9]|1[0-2])\\d{2}|[a-z]{3}/[a-z]{2}/\\d{2}/\\d{3}/\\d{4})$",
  "Hidalgo" = "^(?i)(?:(?:0[1-9]|1\\d|20)(?:[-/]?\\d{4})(?:[-/]?\\d+)|fed[-/]hgo[-/]?[a-z]+(?:[-/]?\\d+)(?:[-/]?\\d{4}))$",
  "Jalisco" = "^(?i)[0-9-]+(?:[-/]?[a-z0-9-]+)(?:[-/]?\\d{4})$",
  "México" = "^(?i)(?:[a-z0-9]{3}(?:[-/]?[a-z0-9]{3})(?:[-/]?(?:[a-z0-9]{3}[-/]?\\d{3}[-/]?\\d{6}|\\d{2}[-/]?[a-z0-9]{3}[-/]?\\d{3}[-/]?\\d{5}))[-/]?\\d{2}[-/]?(0[1-9]|1[0-2]))$",
  "Morelos" = "^(?i)[a-z0-9]+(?:[-/]?\\d+)(?:[-/]?\\d{4})$",
  "Nuevo León" = "^(?i)[a-z0-9]+[-/]?\\d{4}$",
  "Oaxaca" = "^(?i)\\d+(?:[-/]?[a-z0-9-]+)(?:[-/]?\\d{4})$",
  "Querétaro" = "^(?i)(?:ci[-/]?(?:[a-z]{3}[-/]?)?\\d+[-/]?\\d{4}|[1-4][-/]\\d+[-/]\\d+[-/]\\d+[-/]\\d{2}|[ivxlc]+[-/]?\\d+[-/]?\\d{4})$",
  "San Luis Potosí" = "^(?i)(?:cdi|csc)(?:[-/]?fge)(?:[-/]?(?:i|ii|iii|iv|v|vi))(?:[-/]?d(?:0[1-9]|1[0-3]))(?:[-/]?\\d{5})(?:[-/]?\\d{2})$",
  "Sinaloa" = "^(?i)(?:[a-z]{3,6}(?:[-/]?[a-z0-9]{2,10})(?:[-/]?\\d{3,})(?:[-/]?\\d{4})(?:[-/]?[a-z]{1,3})?|[a-z0-9]{3}(?:[-/]?\\d+)(?:[-/]?\\d{4}))$",
  "Sonora" = "^(?i)[a-z0-9]{1,5}(?:[-/]?[a-z0-9]{1,5})(?:[-/]?[a-z0-9]{1,5})(?:[-/]?\\d{1,4})(?:[-/]?[a-z0-9]{1,5})(?:[-/]?\\d+)$",
  "Tabasco" = "^(?i)ci[-/][a-z0-9_]{2,20}(?:[-/][a-z0-9_]{1,20}){0,3}[-/]?\\d+[-/]?\\d{4}$",
  "Tamaulipas" = "^(?i)(?:fgjt(?:[-/][a-z0-9]+){2,5}[-/]\\d+[-/]\\d{4}|\\d{2}[-/]?\\d{2}[-/]?\\d{3}[-/]?\\d+[-/]?\\d{4})$",
  "Tlaxcala" = "^[A-Za-z0-9. ]+[-/]?[0-9]+[-/]?[0-9]+[-/]?[0-9]{4}$",
  "Veracruz" = "^(?i)(?:[a-z0-9]{1,6}(?:[-/]?\\d+)(?:[-/]?\\d{2,4})|(?:[a-z0-9]{1,12}[-/])+(?:feadpd|fedfp|fepd|feiddfpdcp|fedfpdcp|feiddfp|fedfpm)(?:[-/][a-z0-9]{1,12})*[-/]\\d+[-/]\\d{2,4})$",
  "Yucatán" = "^(?i)(?:[a-z0-9]{2}(?:[-/]?\\d{6})(?:[-/]?\\d{4})|fge(?:[-/]?[a-z0-9._áéíóúñ_ -]+)(?:[-/]?[a-z0-9._ -]+)(?:[-/]?\\d{4}))$",
  "Zacatecas" = "^(?i)(?:fgjez(?:[-/]?[a-z0-9_-]+)(?:[-/]?[a-z0-9_-]+)(?:[-/]?\\d+)(?:[-/]?\\d{4}[-/]?(?:0?[1-9]|1[0-2]))|\\d+[-/]?\\d{4}[-/]?(?:0?[1-9]|1[0-2])|av[-/]?\\d+[-/]?\\d{4}[-/]?(?:0?[1-9]|1[0-2]))$",
  "Nayarit" = "^(?i)nay(?:[-/]?[a-z0-9]{2,5})(?:[-/]?m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))(?:[-/]?(?:ci|rh))(?:[-/]?\\d{5,7})(?:[-/]?\\d{4})$",
  "Michoacán" = "^[A-Za-z0-9]{2,10}[-/]?[0-9]+(?:[-/]?[0-9]+)?[-/]?[0-9]{4}$",
  "Puebla" = "^(?i)FGEP/CDI/[A-Za-z0-9.\\- ]+/[A-Za-z0-9.\\- ]+/[0-9]+/[0-9]{4}$",
  "Quintana Roo" = "^(?i)(?:FGE/QROO|CI)(?:/[A-Z0-9]+)+/?$"
)

# ————————————————————————————————————————————————————————— #
# Función de procesamiento de variables (procesamiento_base_final) -----
# ————————————————————————————————————————————————————————— #

#' Procesar y enriquecer las variables de la base final del RNPDNO
#'
#' A partir del archivo .parquet generado por [automatizar_base_final_rnpdno()]
#' (localizado por `fecha_corte`), separa los bloques DESAPARECIDAS,
#' ACTUALIZACION_PENDIENTE y LOCALIZADAS (columna `hoja`), los vuelve a unir
#' en una sola tabla y aplica, en
#' orden: 1) conversión de fechas a Date; 2) invalidación de `fechalocaliza`
#' cuando es anterior a `fechahechos` o posterior a `fecha_corte`;
#' 3) creación de `fecha_hechos_modificada` (coalesce de
#' fechahechos/fechapercato/fechacaptura) y sus variables de año;
#' 4) validación de `curp_victima` con [es_curp_valida()]; 5) imputación de
#' `fechalocaliza_imputada` para Localizados y corrección de
#' `fecha_hechos_modificada` cuando la excede; 6) variables de año/mes
#' derivadas; 7) entidad de desaparición y de nacimiento (join con
#' `catalogo_estados_inegi`) y `cvegeo` (join con `catalogo_municipios_inegi`);
#' 8) `indicadora_carpeta` según si `expediente` cumple el regex de
#' `catalogo_regex_ci_por_entidad` correspondiente a la entidad;
#' 9) reclasificación de `dependencia_origen` (ver
#' [limpiar_dependencia_original()]); 10) cruce con `registros` para
#' `indicadora_indicio_de_vida`; 11) `edad_al_momento_desaparicion` y
#' `grupo_etario`.
#'
#' @param fecha_corte Fecha (character o Date) usada para: ubicar el archivo
#'   `base_final_reporte_personas_<fecha_corte>.parquet` a procesar, e invalidar
#'   fechas de localización posteriores a este corte.
#' @param registros Data frame de registros administrativos de indicios de
#'   vida (defunción, PUI, etc.), con columnas `fub` e
#'   `indicadora_indicio_de_vida`.
#' @param catalogo_estados_inegi Data frame del catálogo de entidades del
#'   INEGI, con columnas `cve_ent` y `nom_ent`.
#' @param catalogo_municipios_inegi Data frame del catálogo de municipios del
#'   INEGI, con columnas `cvegeo` y `nom_mun`.
#' @return Data frame único (`desaparecidos_pendientes_localizados`) con las
#'   tres hojas unidas y todas las variables derivadas descritas arriba.
#' @note Se detiene con `stop()` si no encuentra el archivo
#'   `base_final_reporte_personas_<fecha_corte>.parquet` en
#'   `RNPDNO/output/bases_procesadas_rnpdno/<mes>/actualizacion_<fecha>/`.
procesamiento_base_final <- function(fecha_corte , registros, catalogo_estados_inegi, catalogo_municipios_inegi) {

  fecha_corte <- as.Date(fecha_corte)

  # Derivar todas las variables de fecha desde el parámetro de fecha de corte, para asegurar que el código sea reproducible y no dependa de la fecha actual del sistema
  fecha_workbook <- format(fecha_corte, "%d%m%Y")
  mes_folder     <- format(fecha_corte, "%B_%Y")

  fecha_workbook <- as.character(fecha_workbook)
  mes_folder     <- as.character(mes_folder)

  ## ------ 1. Descargar la base de datos actualizada del RNPDNO ----- ##

  nombre_base <- paste0("base_final_reporte_personas_", fecha_workbook, ".parquet")
  ruta_base_final <- here::here("RNPDNO", "output", "bases_procesadas_rnpdno",
  mes_folder, paste0("actualizacion_", fecha_workbook), nombre_base)
  
  if(!file.exists(ruta_base_final)){
    stop(paste0("ERROR: No se encuentra el archivo en: ", ruta_base_final))
  } else {
    message(paste0("Archivo localizado exitosamente: ", nombre_base, "\n"))
  }
  
  ## ----- Funciones auxiliares ----- ##

  # Regex usadas en la validación de curps
  curp_regex <- "^[A-Z]{4}\\d{6}[HM]"
  curp_regex2 <- "[A-Z]{3}.{2}$"
  
  # Códigos de estado válidos en las curps
  codigos_validos_curp <- c(
    "AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR",
    "HG", "JC", "MC", "MN", "MS", "NT", "NL", "OC", "PL", "QT", "QR", "SP",
    "SL", "SR", "TC", "TS", "TL", "VZ", "YN", "ZS", "NE")
  
  es_curp_valida <- function(curp) {
    grepl(curp_regex, curp, ignore.case = TRUE) &
      grepl(curp_regex2, curp, ignore.case = TRUE) &
      nchar(curp) == 18 &
      substr(curp, 12, 13) %in% codigos_validos_curp
  }
  
  ## ---- Cargar datos ----- ##

  base_final_larga <- arrow::read_parquet(ruta_base_final)

  localizados <- base_final_larga |>
    filter(hoja == "LOCALIZADAS") |>
    select(-hoja) # Cargar localizados
  desaparecidos <- base_final_larga |>
    filter(hoja == "DESAPARECIDAS") |>
    select(-hoja) # Cargar desaparecidos
  pendientes <- base_final_larga |>
    filter(hoja == "ACTUALIZACION_PENDIENTE") |>
    select(-hoja) # Cargar pendientes (es decir, personas desaparecidas sin curp)
  
  # Indicadora de a que tabla pertenecen
  desaparecidos$clasificacion_des <- "Desaparecidos"
  pendientes$clasificacion_des <- "Pendientes"
  localizados$clasificacion_des <- "Localizados"
  
  ## ----- Unión de bases ----- ##
  
  # Eliminar columnas no usadas de desaparecidos y pendientes
  
  cols_validas_desaparecidos <- setdiff(
    names(desaparecidos), 
    c("indicadora_curp_valida", "indicadora_curp_valida_final")
  )
  cols_validas_pendientes <- setdiff(
    names(pendientes), 
    c("indicadora_curp_valida", "indicadora_curp_valida_final")
  )
  
  desaparecidos <- desaparecidos |> 
    select(all_of(cols_validas_desaparecidos))
  
  pendientes <- pendientes |> 
    select(all_of(cols_validas_pendientes))

  
  # Unir las filas de las 3 tablas
  desaparecidos_pendientes_localizados <- 
  bind_rows(
    desaparecidos |> mutate(fechanacimiento = lubridate::as_date(fechanacimiento)),
    pendientes    |> mutate(fechanacimiento = lubridate::as_date(fechanacimiento)),
    localizados   |> mutate(fechanacimiento = lubridate::as_date(fechanacimiento))
  ) |> clean_names() # Limpiar nombres de columnas
  
  # ----- 2. Procesamiento de la tabla final ------
  
  ## Convertir fechas a date -----
  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(across(
      c(fechahechos, fechalocaliza, fechanacimiento, fechapercato, fechacaptura),
      as.Date
    ))
    
  
  ## Eliminar fechas de localización inválidas ----
  
  # 1er criterio, fecha de localización debe ser posterior a fecha de hechos
  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(fechalocaliza = case_when(
      fechahechos > fechalocaliza ~ as.Date(NA),
      TRUE ~ fechalocaliza
    ))
  
  # 2do criterio, fecha
  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(fechalocaliza = case_when(
      fechalocaliza > as.Date(fecha_corte) ~ as.Date(NA), 
      TRUE ~ fechalocaliza
    ))
  
  # Crear fecha_hechos_modificada -----
  desaparecidos_pendientes_localizados <-
    desaparecidos_pendientes_localizados |> 
    mutate(fecha_hechos_modificada = case_when(
      !is.na(fechahechos) ~ fechahechos,
      is.na(fechahechos) & !is.na(fechapercato) ~ fechapercato,
      is.na(fechahechos)&is.na(fechapercato) & !is.na(fechacaptura)~ fechacaptura,
      TRUE ~ NA
    ))
  
  # Crear variables de año -----
  desaparecidos_pendientes_localizados$anio_localizado <- year(
    desaparecidos_pendientes_localizados$fechalocaliza) # Anio de localización
  
  desaparecidos_pendientes_localizados$anio_hechos <- year(
    desaparecidos_pendientes_localizados$fechahechos) # Anio de hechos
  
  desaparecidos_pendientes_localizados$anio_hechos_modificada <- year(
    desaparecidos_pendientes_localizados$fecha_hechos_modificada) # Anio coalesce
  

  ## ---- 3. Crear indicadora de curp válida ------ ##

  # Si existe la columna curp_vic entonces renombrarla a curp_victima
  if("curp_vic" %in% names(desaparecidos_pendientes_localizados)) {
    desaparecidos_pendientes_localizados <- 
      desaparecidos_pendientes_localizados |> 
      rename(curp_victima = curp_vic)
  }

  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(indicadora_curp_valida = ifelse(
      es_curp_valida(curp_victima),
      "valida",
      "invalida"))
  
  ## ----- 4. Imputación de fecha de localización ----- ##
  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(fechalocaliza_imputada = if_else(
      is.na(fechalocaliza) & clasificacion_des == "Localizados", 
      fecha_hechos_modificada, 
      fechalocaliza
    ))
  
  desaparecidos_pendientes_localizados$anio_loc_imputada <-
    year(desaparecidos_pendientes_localizados$fechalocaliza_imputada)

  # Corrección de fecha de hechos cuando esta sea mayor a la fecha de localización inputada 
  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(fecha_hechos_modificada = case_when(
      fecha_hechos_modificada > fechalocaliza_imputada ~ fechalocaliza_imputada, 
      TRUE ~ fecha_hechos_modificada
    ))
  
  ## ----- 5. Variables de año y mes de localización y hechos modificada ----- ##
  desaparecidos_pendientes_localizados$anio_hechos_modificada <- year(desaparecidos_pendientes_localizados$fecha_hechos_modificada)

  desaparecidos_pendientes_localizados$mes_hechos_modificada  <- month(desaparecidos_pendientes_localizados$fecha_hechos_modificada)

  desaparecidos_pendientes_localizados$mes_loc_imputada       <- month(desaparecidos_pendientes_localizados$fechalocaliza_imputada)

  desaparecidos_pendientes_localizados <-
    desaparecidos_pendientes_localizados |> 
    mutate(
      anio_mes_hechos_modificada = make_date(anio_hechos_modificada, mes_hechos_modificada, 1),
      anio_mes_loc_imputada      = make_date(anio_loc_imputada, mes_loc_imputada, 1)
    )
  
  ## ------ 6. Entidad federativa de desaparición y nacimiento ----- ##

  # Join con catálogo de estados — eliminamos columna previa si existe
  if ("estado" %in% names(desaparecidos_pendientes_localizados)) {
    desaparecidos_pendientes_localizados <-
      desaparecidos_pendientes_localizados |> select(-estado)
  }
  
  # Pegamos el catálogo de estados con rnpdno (comprimido)
  desaparecidos_pendientes_localizados <- desaparecidos_pendientes_localizados |> 
    mutate(idestado = as.character(idestado)) |>
    mutate(idestado = str_pad(idestado, width = 2, side = "left", pad = "0")) |>
    left_join(catalogo_estados_inegi, by = c("idestado" = "cve_ent")) |> 
    rename(estado_desaparicion = nom_ent)

  # Aseguramos que todo desaparecido con idestado igual a "33" tenga la etiqueta correcta a "Se desconoce"
  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(estado_desaparicion = if_else(idestado == "33", "Se desconoce", estado_desaparicion))

  # Pegamos el catálogo de estados con rnpdno (comprimido) para la variable de estado de nacimiento
  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados|> 
      mutate(
       idestadonacimiento_vic = str_pad(idestadonacimiento_vic, width = 2, side = "left", pad = "0")
     ) |> 
    left_join(catalogo_estados_inegi, by = c("idestadonacimiento_vic" = "cve_ent")) |> 
    rename(entidad_nacimiento_nom = nom_ent)

  desaparecidos_pendientes_localizados <-
    desaparecidos_pendientes_localizados|> 
    mutate(entidad_nacimiento_nom = if_else(idestadonacimiento_vic == 33, "Nacido en el extranjero", entidad_nacimiento_nom))

  # Crear variable de cvegeo
  desaparecidos_pendientes_localizados <-
    desaparecidos_pendientes_localizados |> 
    mutate(
      idestado = str_pad(idestado, width = 2, pad = "0"),
      # Cambio el 02 de oct-2026. Debido a que 'idmunicipio' ahora viene en el formato '5.0' tenemos que quitar el '.0' y convertirlo a entero antes de hacer el str_pad. Esto es para evitar que se genere un cvegeo incorrecto.
      idmunicipio = as.character(as.integer(as.numeric(idmunicipio))),
      idmunicipio = str_pad(idmunicipio, width = 3, pad = "0"),
      cvegeo = ifelse(!is.na(idestado) & !is.na(idmunicipio), paste0(idestado, idmunicipio), NA)
      )
  
  # Pegar catálogo de municipios para obtener nombre del municipio
  desaparecidos_pendientes_localizados <-
    desaparecidos_pendientes_localizados |>
    left_join(catalogo_municipios_inegi |> clean_names() |> select(cvegeo, municipio_desaparicion = nom_mun), by = c("cvegeo" = "cvegeo"))

  # Homologar nombres de columnas de idestado y idmunicipio
  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |>
    rename(
      cve_estado_desaparicion = idestado,
     cve_municipio_desaparicion = idmunicipio
          )

  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |>
    rename(
      cvegeo_desaparicion = cvegeo
        )
  
    ## ---- 7. Validación de investigación ----- ##
  
    ## Crear indicadora de carpeta ------
    # Modificación al 03 de julio de 2026: Vamos a usar catalogo_regex_ci_por_entidad para validar si el expediente es una carpeta de investigación válida según la entidad federativa. Si el expediente cumple con el regex correspondiente a la entidad, se clasificará como "Con carpeta", de lo contrario, como "Sin carpeta".
    # Se itera sobre las ~32 entidades del catálogo y se aplica grepl()
    # vectorizado sobre el subconjunto de filas de cada entidad, en vez de
    # evaluar fila por fila.
  
    # Si no existe columna "expediente" pero sí "expediente_vic", "expedientes" o "expediente_victima" renombrarla a
    # "expediente"
    if(! "expediente" %in% names(desaparecidos_pendientes_localizados)) {
      if("expediente_vic" %in% names(desaparecidos_pendientes_localizados)){
        desaparecidos_pendientes_localizados <- 
          desaparecidos_pendientes_localizados |> 
          rename(expediente = expediente_vic)
      } else if("expedientes" %in% names(desaparecidos_pendientes_localizados)){
        desaparecidos_pendientes_localizados <- 
          desaparecidos_pendientes_localizados |> 
          rename(expediente = expedientes)
      } else if("expediente_victima" %in% names(desaparecidos_pendientes_localizados)){
        desaparecidos_pendientes_localizados <- 
          desaparecidos_pendientes_localizados |> 
          rename(expediente = expediente_victima)
      } else {
        stop("No se encontró ninguna columna de expediente de carpeta válida en la tabla desaparecidos_pendientes_localizados. Por favor hay que asegurarnos de que exista.")
      }
    }
    
    desaparecidos_pendientes_localizados <-
      desaparecidos_pendientes_localizados |>
      mutate(
        expediente = str_remove_all(expediente, "\\s+"), # Eliminar espacios en blanco
        estado_desaparicion = trimws(estado_desaparicion),
        match_ci = FALSE
    )

    for (entidad in names(catalogo_regex_ci_por_entidad)) {
      pat <- catalogo_regex_ci_por_entidad[[entidad]]
      if (is.na(pat)) next

      filas <- which(
        desaparecidos_pendientes_localizados$estado_desaparicion == entidad &
          !is.na(desaparecidos_pendientes_localizados$expediente) &
          desaparecidos_pendientes_localizados$expediente != ""
      )

      if (length(filas) > 0) {
        desaparecidos_pendientes_localizados$match_ci[filas] <- grepl(
          pat,
          desaparecidos_pendientes_localizados$expediente[filas],
          perl = TRUE,
          ignore.case = TRUE
        )
      }
    }
    
  # Segunda capa (Oaxaca): las siglas del folio deben existir en el catálogo
    siglas_validas_oaxaca <- toupper(trimws(catalogo_nomenclatura_oaxaca_todos$nomenclatura))
    
    filas_oax <- which(
      desaparecidos_pendientes_localizados$estado_desaparicion == "Oaxaca" &
      desaparecidos_pendientes_localizados$match_ci
    )
    
    if (length(filas_oax) > 0) {
    # Captura lo que hay entre el consecutivo inicial y el año final
    siglas_folio <- str_match(
      desaparecidos_pendientes_localizados$expediente[filas_oax],
      "^\\d+[-/]?(.+?)[-/]?\\d{4}$"
    )[, 2]

     desaparecidos_pendientes_localizados$match_ci[filas_oax] <-
      toupper(siglas_folio) %in% siglas_validas_oaxaca
    }

    desaparecidos_pendientes_localizados <-
      desaparecidos_pendientes_localizados |>
      mutate(indicadora_carpeta = if_else(match_ci, "Con carpeta", "Sin carpeta")) |>
      select(-match_ci)

  ## ----- validación anterior ---- ##
  # desaparecidos_pendientes_localizados <- 
  #   desaparecidos_pendientes_localizados |> 
  #   mutate(indicadora_carpeta = ifelse(
  #     grepl("\\bAP\\b|\\b(CI|CDI)\\b", expediente, ignore.case = T), 
  #     "Con carpeta", 
  #     "Sin carpeta"
  #   ))
  
  ## ------- 8. Crear indicadora de dependencias ------ ##

  # Un caso con indicadora_carpeta == "con carpeta" se clasificará como "carpeta de investigación". Igualmente, si el valor de indicadora_carpeta es "sin carpeta" (es decir, con expediente no válido como carpeta de investigación o con valor vacío) entonces se clasifica como "expediente genérico"

  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(
    expediente_reclasif = case_when(
      indicadora_carpeta == "Con carpeta" ~ "carpeta de investigacion",
      indicadora_carpeta == "Sin carpeta" ~ "expediente genérico"
     )
    )

  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    mutate(dependencia_origen_reclasificado = case_when(
    
    # 1. FISCALÍAS (Con su subdivisión interna)
    grepl("FISCALIA|FISCAL|PROCURADUR|SUBPROCURADURIA", dependencia_origen, ignore.case = TRUE) & 
      expediente_reclasif == "carpeta de investigacion" ~ "Fiscalía con carpeta de investigación",
    
    grepl("FISCALIA|FISCAL|PROCURADUR|SUBPROCURADURIA", dependencia_origen, ignore.case = TRUE) & 
      expediente_reclasif == "expediente genérico" ~ "Fiscalía con expediente genérico",
    
    # Por si hay alguna fiscalía que no tiene ni CI ni expediente genérico
    grepl("FISCALIA|FISCAL|PROCURADUR|SUBPROCURADURIA", dependencia_origen, ignore.case = TRUE) ~ "Fiscalía (otra)",
    
    # 2. COMISIONES (Específicas)
    grepl("^COMISION NACIONAL DE BUSQUEDA", dependencia_origen, ignore.case = TRUE) ~ "Comisión Nacional de búsqueda de personas",
    grepl("^COMISION LOCAL", dependencia_origen, ignore.case = TRUE) ~ "Comisión local de búsqueda de personas",
    
    # 3. Otras categorías
    grepl("^COMISI", dependencia_origen, ignore.case = TRUE) ~ "Otra comisión",
    grepl("^PORTAL", dependencia_origen, ignore.case = TRUE) ~ "Portal",
    
    # 4. Lo que no entró en nada de lo anterior, se queda como estaba
    TRUE ~ dependencia_origen
  ))

  # Limpiar dependencia_origen
  desaparecidos_pendientes_localizados <- limpiar_dependencia_original(
    comprimido = desaparecidos_pendientes_localizados,
    catalogo_estados_inegi = catalogo_estados_inegi 
)
  
  ## ---- 9. Pegar con los indicios de vida ---- ##
  # Por practicidad fijamos todos los indicios de vida (incluyendo fallecidos) como "con registros administrativo"
  registros <- registros |> 
    mutate(
      indicadora_indicio_de_vida = case_when(
        indicadora_indicio_de_vida == "con registro administrativo" ~ "con registro administrativo",
        indicadora_indicio_de_vida == "defuncion" ~ "con registro administrativo",
        indicadora_indicio_de_vida == "con registro administrativo en PUI" ~ "con registro administrativo",
        TRUE ~ "sin registro administrativo"
      )
    )

  desaparecidos_pendientes_localizados <- 
    desaparecidos_pendientes_localizados |> 
    left_join(registros |> select(fub, indicadora_indicio_de_vida), by = "fub") |> 
    distinct(fub, .keep_all = TRUE) |> 
    mutate(indicadora_indicio_de_vida = case_when(
      is.na(indicadora_indicio_de_vida) ~ "sin registro administrativo",
      TRUE ~ indicadora_indicio_de_vida
    ))
  
  desaparecidos_pendientes_localizados <- desaparecidos_pendientes_localizados |> 
   distinct(fub, .keep_all = TRUE) # Nos aseguramos de que no haya registros duplicados por fub

  ## ---- 10. Crear columnas de edad y grupo etario ----- ##

  # crear columna de edad al momento de la desaparición
  desaparecidos_pendientes_localizados <- desaparecidos_pendientes_localizados |> 
    mutate(edad_al_momento_desaparicion = as.integer(difftime(fecha_hechos_modificada, fechanacimiento, units = "days") / 365.25))

  # Creamos una variable de grupo etario
  desaparecidos_pendientes_localizados <- desaparecidos_pendientes_localizados |>
    mutate(
      grupo_etario = case_when(
      is.na(edad_al_momento_desaparicion)                              ~ NA_character_,
      edad_al_momento_desaparicion < 0                                 ~ NA_character_, # edades imposibles
      edad_al_momento_desaparicion <= 11                               ~ "Niñez (0-11)",
      edad_al_momento_desaparicion <= 17                               ~ "Adolescencia (12-17)",
      edad_al_momento_desaparicion <= 29                               ~ "Madurez (18-29)",
      edad_al_momento_desaparicion <= 59                               ~ "Adultez (30-59)",
      edad_al_momento_desaparicion >= 60                               ~ "Adulto o adulta mayor (60+)",
      TRUE                                                             ~ NA_character_
    ),
    # factor ordenado para que los gráficos respeten el orden correcto
    grupo_etario = factor(grupo_etario, levels = c(
      "Niñez (0-11)",
      "Adolescencia (12-17)",
      "Madurez (18-29)",
      "Adultez (30-59)",
      "Adulto o adulta mayor (60+)"
    ))
  )

   # Paso intemedio: limpiar carpeta de archivos de salida
  message("Limpiando carpeta de archivos para conservar solo el archivo procesado (una vez aplicadas las transformaciones necesarias del proceso) de RNPDNO más reciente, más próximo a la mitad del mes y más cercano al final del mes.\n")

  tryCatch(
  {
    withCallingHandlers(
      limpiar_actualizaciones_viejas_rnpdno(
        ruta_guardado_folder = fs::path_dir(fs::path_dir(ruta_base_final)),
        mantener_ultimas = 3,
        tipo_archivo = "salida"
      ),
      warning = function(s) {
        message("[Warning Paso de Limpieza de Carpeta] ", conditionMessage(s), "\n")
        invokeRestart("muffleWarning")
      }
    )
  },
  error = function(e) {
    message("[Error Paso de Limpieza de Carpeta] Error al eliminar y limpiar archivos:\n",
        conditionMessage(e), "\n")
  }
  )


  return(desaparecidos_pendientes_localizados)
}

# ————————————————————————————————————————————————————————— #
# Función para actualizar el RNPDNO y procesar variables (funcion_actualizar_rnpdno_y_procesar_variables) -----
# ————————————————————————————————————————————————————————— #

#' Punto de entrada: actualizar el RNPDNO y procesar sus variables
#'
#' Si `descargar = TRUE`, obtiene el ID del archivo
#' `reporte_personas_completo.parquet` en `Id_carpeta_reporte` o su subcarpeta
#' `cqr` (ver [extraer_id()]) y ejecuta
#' [automatizar_base_final_rnpdno()] para descargar, limpiar y guardar el
#' reporte de personas; si `descargar = FALSE`, usa el archivo ya existente
#' en disco. En ambos casos, siempre ejecuta después
#' [procesamiento_base_final()] para generar la base final con las variables
#' derivadas.
#'
#' @param fecha_corte Fecha (character o Date) de corte; se pasa a
#'   [procesamiento_base_final()] para ubicar el archivo y para invalidar
#'   fechas de localización posteriores.
#' @param registros Data frame de registros administrativos de indicios de
#'   vida. Obligatorio (la función se detiene con `stop()` si es NULL).
#' @param Id_carpeta_reporte Character. ID de la carpeta de Google Drive
#'   donde vive el archivo "reporte_personas". Solo se usa si
#'   `descargar = TRUE`. Default: '1Tgo8oWhoeilWr1J-EB6n22QK7rHUvgN0'.
#' @param catalogo_estados_inegi Data frame del catálogo de entidades del
#'   INEGI, con columnas `cve_ent` y `nom_ent`.
#' @param catalogo_municipios_inegi Data frame del catálogo de municipios del
#'   INEGI, con columnas `cvegeo` y `nom_mun`.
#' @param descargar Lógico. TRUE (default) para descargar y regenerar el
#'   archivo de reporte de personas antes de procesar; FALSE para reutilizar
#'   el archivo ya existente en disco.
#' @param ruta_reporte_local Character o NULL. Ruta a un
#'   `reporte_personas_completo.parquet` descargado manualmente. Si se
#'   proporciona, se ignora `descargar` y se ejecuta
#'   [automatizar_base_final_rnpdno()] sobre ese archivo sin conectarse a
#'   Google Drive. Default: NULL.
#' @return El data frame final generado por [procesamiento_base_final()].
actualizar_rnpdno_y_procesar <- function(fecha_corte,
                                          registros,
                                          Id_carpeta_reporte =  '1Tgo8oWhoeilWr1J-EB6n22QK7rHUvgN0',
                                          catalogo_estados_inegi,
                                          catalogo_municipios_inegi,
                                          descargar = TRUE,
                                          ruta_reporte_local = NULL
                                        )
                                          {  
  
  # Validación: registros es obligatorio
  if (is.null(registros)) {
    stop("El argumento 'registros' es obligatorio. Proporciona la base de registros de indicios de vida actualizada.")
  } else {
    message("Base de registros de indicios de vida proporcionada correctamente.\n")

    message(paste0("El número de registros únicos por fub en la base de coincidencias administrativas es: ", comma(nrow(registros)), ".\n"))
  }
  
  tiempo_total <- system.time({
    # Paso 1: Descargar y generar el .xlsx (solo si se pide)
    tiempo_paso_1 <- system.time({
      if (!is.null(ruta_reporte_local)) {
        message("Procesando el archivo de reporte de personas descargado manualmente (sin Google Drive)...")

        automatizar_base_final_rnpdno(ruta_reporte_local = ruta_reporte_local)
      } else if (descargar) {
        message("Descargando y procesando el archivo de reporte de personas desde Google Drive...")

        id_archivo_reporte_personas <- extraer_id(Id_carpeta_reporte)

        automatizar_base_final_rnpdno(
          id_archivo_reporte_personas = id_archivo_reporte_personas
        )
      } else {
        message("Omitiendo descarga: se usará el archivo ya existente en disco.\n")
      }
    })
    message("Tiempo Paso 1 (descarga/lectura del reporte de personas): ", round(tiempo_paso_1["elapsed"], 1), " s\n")

    message("Procesando variables de la base final del RNPDNO...\n")

    # Paso 2: Procesar siempre
    tiempo_paso_2 <- system.time({
      resultado <- procesamiento_base_final(
        fecha_corte               = fecha_corte,
        registros                 = registros,
        catalogo_estados_inegi    = catalogo_estados_inegi,
        catalogo_municipios_inegi = catalogo_municipios_inegi
      )
    })
    message("Tiempo Paso 2 (procesamiento_base_final): ", round(tiempo_paso_2["elapsed"], 1), " s\n")
  })

  message("Tiempo total de actualizar_rnpdno_y_procesar(): ", round(tiempo_total["elapsed"], 1), " s\n")

  message("¡Actualización y procesamiento del RNPDNO completados con éxito!")

  # Regresar resultado
  return(resultado)
}