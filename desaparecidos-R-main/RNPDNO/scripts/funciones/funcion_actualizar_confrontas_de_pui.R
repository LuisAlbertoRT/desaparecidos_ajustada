# ————————————————————————————————————————————————————————— #
# Nombre: Jocelyn Rocha
# Contacto: maricelaymiel@gmail.com
# Script: funcion_confrontas_manuales_con_pui.R
# Proyecto: Personas Desaparecidas
# Fecha: 2026-05-15
# Propósito: Función que puede hacer dos cosas 1. actualizar el archivo de confrontas administrativas y 2. actualizar el archivo del RNPDNO (comprimido)
# ————————————————————————————————————————————————————————— #
# Librerías -----
# ————————————————————————————————————————————————————————— #

pacman::p_load(
  readr, tidyverse, dplyr, lubridate, readxl,
  scales, magrittr, stringi, tsibble, svglite,
  here, janitor, officer, reticulate, purrr,
  glue
)

# ————————————————————————————————————————————————————————— #
# Archivos recurrentes -----
# ————————————————————————————————————————————————————————— #

# Obtenemos datos de la carpeta compartida de Drive:
readRenviron(".Renviron")
Sys.getenv("RNPDNO_data_raiz")

raiz_datos <- function(...) {
  raiz <- Sys.getenv("RNPDNO_data_raiz", unset = here::here())
  file.path(raiz, ...)
}

# ----- Defunciones ------ #
carpeta_matches_historicos_output <- raiz_datos("Confrontas", "output")

defunciones_df <- openxlsx::read.xlsx(
  file.path(
    carpeta_matches_historicos_output,
    "resumen_todas_confrontas_historicas",
    "resultados_05052026",
    "tabla_defunciones_por_institucion_05052026.xlsx"
  )
)

# ————————————————————————————————————————————————————————— #
# Paso 1. Descargar archivo de carpeta de Google Drive -----
# ————————————————————————————————————————————————————————— #

# Se definen las cadenas de carácteres de las urls para la descarga del archivo desde Google Drive. Se recomienda no modificar estas cadenas, ya que son parte de la lógica para extraer los IDs necesarios para la descarga.

#' Descargar y extraer el CSV más reciente desde un ZIP en Google Drive
#'
#' Busca en una carpeta de Google Drive el archivo ZIP con el nombre indicado,
#' descarga la versión más reciente (según fecha de modificación), lo
#' descomprime y extrae el primer CSV que encuentre dentro (el archivo .csv
#' que se necesita siempre viene guardado en un ZIP). Los archivos quedan en
#' una subcarpeta \code{<mes_actual>/actualizacion_<ddmmyyyy>} dentro de
#' \code{ruta_actual}, que se crea si no existe.
#'
#' @param ruta_actual Character. Carpeta base donde se crean las subcarpetas
#'   de mes y de actualización para guardar el ZIP y el CSV extraído.
#' @param nombre_archivo_zip Character. Nombre exacto del archivo ZIP a buscar
#'   dentro de la carpeta de Google Drive (\code{id_carpeta}).
#' @param id_carpeta Character. ID de la carpeta de Google Drive (tal como lo
#'   espera \code{googledrive::as_id()}) donde se busca el ZIP.
#' @param patron_csv Character. Expresión regular para identificar el CSV
#'   dentro del ZIP. Por defecto \code{"\\.csv$"} (cualquier archivo con
#'   extensión .csv). Si hay varias coincidencias, se usa la primera.
#'
#' @return Lista con tres elementos:
#'   \item{ruta_zip}{Ruta local del ZIP descargado.}
#'   \item{ruta_csv}{Ruta local del CSV extraído.}
#'   \item{carpeta_actualizacion}{Carpeta donde quedaron el ZIP y el CSV.}
#'
#' @examples
#' \dontrun{
#' res <- descarga_y_extrae_csv_desde_zip(
#'   ruta_actual = here::here("RNPDNO", "input", "datos_procesados_de_la_pui"),
#'   nombre_archivo_zip = paste0("reporte_coincidencias_validas_", Sys.Date(), ".zip"),
#'   id_carpeta = "1BMB5LR9rGImky6KJccM_ENeF4E6_DlPj"
#' )
#' }
descarga_y_extrae_csv_desde_zip <- function(ruta_actual,
                                             nombre_archivo_zip, 
                                             id_carpeta,  # Cambié el nombre del parámetro
                                             patron_csv = "\\.csv$") {
  
  fecha_actual <- lubridate::today()
  mes_folder <- format(fecha_actual, "%B_%Y")
  ruta_guardado_folder <- fs::path(ruta_actual, mes_folder)
  if (!fs::dir_exists(ruta_guardado_folder)) fs::dir_create(ruta_guardado_folder)
  
  fecha_actual_carpeta <- format(fecha_actual, "%d%m%Y")
  actualizacion_mes_folder <- paste0("actualizacion_", fecha_actual_carpeta)
  ruta_guardado_actualizacion <- fs::path(ruta_actual, mes_folder, actualizacion_mes_folder)
  if (!fs::dir_exists(ruta_guardado_actualizacion)) fs::dir_create(ruta_guardado_actualizacion)
  
  # 1) Listar archivos en la carpeta y buscar el ZIP más reciente
  archivos_en_carpeta <- googledrive::drive_ls(path = googledrive::as_id(id_carpeta))
  
  # Filtrar por nombre del archivo ZIP
  archivos_zip <- archivos_en_carpeta |> 
    filter(name == nombre_archivo_zip)
  
  if (nrow(archivos_zip) == 0) {
    stop("No se encontró ningún archivo con el nombre: ", nombre_archivo_zip)
  }
  
  # Obtener información detallada para ver fechas de modificación
  archivos_zip_detalle <- archivos_zip |> 
  mutate(
    fecha_modificacion = map_chr(id, ~{
      info <- googledrive::drive_get(googledrive::as_id(.x))
      info$drive_resource[[1]]$modifiedTime
    })
  )

  # Ordenar por fecha de modificación (más reciente primero)
  archivo_mas_reciente <- archivos_zip_detalle |> 
    arrange(desc(fecha_modificacion)) |> 
    slice(1)
  
    message("Archivo más reciente encontrado: ", archivo_mas_reciente$name, 
          " (modificado: ", archivo_mas_reciente$fecha_modificacion, ")")
  
    # 2) Descargar ZIP más reciente
    ruta_zip <- fs::path(ruta_guardado_actualizacion, nombre_archivo_zip)
    googledrive::drive_download(
      file = googledrive::as_id(archivo_mas_reciente$id),
      path = ruta_zip,
      overwrite = TRUE
    )
  
    if (!file.exists(ruta_zip)) stop("No se descargó el ZIP.")
  
    # 3) Ver contenido ZIP
    contenido_zip <- utils::unzip(ruta_zip, list = TRUE)
    csvs <- contenido_zip$Name[grepl(patron_csv, contenido_zip$Name, ignore.case = TRUE)]
    if (length(csvs) == 0) stop("El ZIP no contiene CSV.")
  
    csv_objetivo <- csvs[1]
  
    # 4) Extraer CSV
    utils::unzip(
      zipfile = ruta_zip,
      files = csv_objetivo,
      exdir = ruta_guardado_actualizacion,
      overwrite = TRUE
    )
  
    ruta_csv <- fs::path(ruta_guardado_actualizacion, csv_objetivo)
    if (!file.exists(ruta_csv)) stop("No se pudo extraer el CSV.")
  
    return(list(
      ruta_zip = ruta_zip,
      ruta_csv = ruta_csv,
      carpeta_actualizacion = ruta_guardado_actualizacion
    ))
}

#' Conservar solo 3 carpetas de actualización por mes
#'
#' Dentro de una carpeta de mes que contiene subcarpetas
#' \code{actualizacion_<ddmmyyyy>}, conserva únicamente tres: la más antigua,
#' la más cercana a la mitad del mes y la más reciente; el resto se elimina
#' del disco. Si hay \code{mantener_ultimas} carpetas o menos, no se borra nada.
#'
#' @param ruta_guardado_folder Character. Carpeta de mes que contiene las
#'   subcarpetas \code{actualizacion_*} a evaluar. El nombre de cada
#'   subcarpeta debe terminar en una fecha \code{ddmmyyyy}.
#' @param mantener_ultimas Integer. Umbral: si hay esta cantidad de carpetas
#'   o menos, no se borra nada. Por defecto \code{3}. Nota: aunque este
#'   umbral es configurable, la función siempre intenta conservar
#'   exactamente 3 fechas (inicio, mitad y fin de mes), sin importar su valor.
#'
#' @return \code{invisible(NULL)}. Efecto secundario: borra del disco las
#'   carpetas de actualización que no correspondan a inicio, mitad o fin de mes.
#'
#' @examples
#' \dontrun{
#' limpiar_actualizaciones_viejas_pui(fs::path_dir(res_descarga$carpeta_actualizacion))
#' }
limpiar_actualizaciones_viejas_pui <- function(ruta_guardado_folder, mantener_ultimas = 3) {
  
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

  # Solo mantener a las carpetas que estén más cerca del inicio, a la mitad y al final del mes
  # Extraemos la fecha del nombre de la carpeta para ordenar correctamente
  # (ordenar alfabéticamente NO funciona bien con fechas DDMMYYYY)
  fechas <- stringr::str_extract(carpetas_actualizacion, "\\d{8}$") |> 
    lubridate::dmy()

  # Fecha más cerca al inicio del mes
  fecha_inicio <- min(fechas)

  # Fecha más cercana del último día del mes
  fecha_fin <- max(fechas)

  # Fecha más cercana a la mitad del mes
  fecha_piso_mes <- floor_date(fecha_inicio, unit = "month")
  fecha_mitad_mes <- fecha_piso_mes + days(14)

  lista_diferencia_dias <- list()

  # Encontrar la fecha en fechas más cercana a fecha_mitad_mes
  for(fecha in fechas) {

    fecha <- as.Date(fecha)

    diferencia_dias <- fecha_mitad_mes - fecha

    diferencia_dias <- as.numeric(diferencia_dias)

    lista_diferencia_dias <- append(lista_diferencia_dias, diferencia_dias)
  }

  # Volver a hacer atómico a la lista
  lista_diferencia_dias <- unlist(lista_diferencia_dias)

  # Escoger el índice más cercano al 0
  ind_lista_diferencia_dias <- which.min(abs(lista_diferencia_dias))
  # Llamar a este valor
  min_lista_diferencia_dias <- lista_diferencia_dias[ind_lista_diferencia_dias]

  # A partir fecha_mitad_mes restarle el min_lista_diferencia_dias
  # Así obtenemos el archivo que se busca conservar
  fecha_mas_cercana_mitad <- fecha_mitad_mes - days(min_lista_diferencia_dias)

  # Ordenar archivos de menor a mayor
  orden <- order(fechas, decreasing = TRUE)
  carpetas_ordenadas <- carpetas_actualizacion[orden]
  
  # Nos quedamos con fecha_inicio , fecha_fin y fecha_mas_cercana_mitad
  fechas_a_conservar <- c(fecha_inicio, fecha_mas_cercana_mitad, fecha_fin)
  carpetas_a_borrar <- carpetas_actualizacion[!fechas %in% fechas_a_conservar]
  
  if (length(carpetas_a_borrar) > 0) {
    fs::dir_delete(carpetas_a_borrar)
    message("Se eliminaron ", length(carpetas_a_borrar), " carpetas de actualizaciones viejas.")
  }
}

#' Leer un CSV de la PUI probando codificaciones
#'
#' Intenta leer el archivo con codificación UTF-8 y, si falla, reintenta con
#' Latin1. Al final normaliza los nombres de columna con
#' \code{janitor::clean_names()}.
#'
#' @param ruta_csv Character. Ruta al archivo CSV a leer.
#'
#' @return Un data.frame (tibble) con los nombres de columna normalizados.
#'
#' @examples
#' \dontrun{
#' coincidencias_admin_con_inactivas <- leer_csv_pui(res_descarga$ruta_csv)
#' }
leer_csv_pui <- function(ruta_csv) {
  # Intento 1: UTF-8
  df <- tryCatch(
    readr::read_csv(
      ruta_csv,
      locale = readr::locale(encoding = "UTF-8"),
      show_col_types = FALSE
    ),
    error = function(e) NULL
  )
  
  # Intento 2: Latin1 si UTF-8 falla
  if (is.null(df)) {
    df <- readr::read_csv(
      ruta_csv,
      locale = readr::locale(encoding = "Latin1"),
      show_col_types = FALSE
    )
  }
  
  janitor::clean_names(df)
}

#' Buscar y leer el archivo de actualización de la PUI más cercano a una fecha
#'
#' Busca, dentro de la carpeta del mes correspondiente, la subcarpeta de
#' actualización cuyo nombre contiene la fecha indicada (en formato
#' `ddmmaaaa`), y lee el archivo de datos (`.xlsx` o `.csv`) que contiene.
#' Si no existe ninguna actualización para esa fecha exacta, se detiene con
#' un error que lista las fechas disponibles ese mes, para facilitar elegir
#' otro día.
#'
#' @param carpeta Ruta a la carpeta raíz de la PUI, dentro de la cual existen
#'   subcarpetas por mes (ej. `"Agosto"`, `"Septiembre"`) y, dentro de cada
#'   una, subcarpetas de actualización con la fecha embebida en el nombre en
#'   formato `ddmmaaaa` (ej. `"14082026_actualizacion"`).
#' @param fecha Fecha a buscar, como string en formato ISO `"aaaa-mm-dd"`
#'   (ej. `"2026-08-14"`) o como objeto `Date`.
#'
#' @return Un data.frame con el contenido del archivo (`.xlsx` o `.csv`)
#'   encontrado dentro de la carpeta de actualización correspondiente a la
#'   fecha buscada.
#'
#' @details Si hay más de una subcarpeta de actualización que hace match con
#'   la fecha buscada, solo se usa la primera (`coincidencias[1]`). Si la
#'   carpeta de actualización encontrada contiene más de un archivo `.xlsx`
#'   o `.csv`, la función tomará el primero que haga match con el patrón de
#'   extensión correspondiente.
#'
#' @examples
#' \dontrun{
#' buscar_archivo_por_fecha(
#'   carpeta = here::here("RNPDNO", "input", "datos_procesados_de_la_pui"),
#'   fecha   = "2026-08-14"
#' )
#' }
buscar_archivo_por_fecha <- function(carpeta, fecha) {

  fecha_date   <- as.Date(fecha)
  patron_fecha <- format(fecha_date, "%d%m%Y")
  regex_fecha  <- paste0("(^|[^0-9])", patron_fecha, "([^0-9]|$)")

  carpetas <- fs::dir_ls(carpeta, type = "directory")

  mes_fecha_date <- format(fecha_date, "%B")
  carpeta_pui <- carpetas[str_detect(carpetas, regex(mes_fecha_date, ignore_case = TRUE))]

  actualizaciones_del_mes_pui <- fs::dir_ls(carpeta_pui, type = "directory")

  coincidencias <- actualizaciones_del_mes_pui[str_detect(actualizaciones_del_mes_pui, regex_fecha)]

  if (length(coincidencias) == 0) {

    # Extraer las fechas (ddmmaaaa) de los nombres de las carpetas que sí existen ese mes
    nombres_disponibles <- fs::path_file(actualizaciones_del_mes_pui)

    fechas_disponibles <- str_match(nombres_disponibles, "(^|[^0-9])(\\d{8})([^0-9]|$)")[, 3] |>
      as.Date(format = "%d%m%Y") |>
      sort() |>
      unique()

    mensaje_disponibles <- if (length(fechas_disponibles) > 0) {
      paste0(
        "Fechas disponibles ese mes: ",
        paste(format(fechas_disponibles, "%Y-%m-%d"), collapse = ", ")
      )
    } else {
      paste0(
        "No se reconoció ninguna fecha en los nombres de carpeta de ese mes. Carpetas encontradas: ",
        paste(nombres_disponibles, collapse = ", ")
      )
    }

    stop(
      "No se encontró ningún archivo local con fecha ", format(fecha_date, "%Y-%m-%d"),
      " (buscado como '", patron_fecha, "') en: ", carpeta, "\n",
      mensaje_disponibles,
      call. = FALSE
    )
  }

  archivos_pui <- fs::dir_ls(coincidencias[1], type = "file")

  if (str_detect(archivos_pui, "\\.xlsx$")) {
    excel_encontrado <- archivos_pui[str_detect(archivos_pui, "\\.xlsx$")]
    df <- readxl::read_excel(excel_encontrado)
  } else {
    csv_encontrado <- archivos_pui[str_detect(archivos_pui, "\\.csv$")]
    df <- leer_csv_pui(csv_encontrado)
  }

  message(
    "Se encontró un archivo con fecha ", format(fecha_date, "%Y-%m-%d"),
    " (buscado como '", patron_fecha, "') en: ", carpeta, "\n"
  )

  return(df)
}

# ————————————————————————————————————————————————————————— #
# Función que depdende de si se cuentan con nuevos datos de la PUI -----
# --------------------------------------------------------- #

#' Actualizar confrontas administrativas de la PUI y el RNPDNO (comprimido)
#'
#' Cruza las coincidencias administrativas de la Plataforma Única de
#' Información (PUI) con las confrontas manuales del RNPDNO y con las
#' defunciones, y usa el resultado para actualizar dos cosas:
#' \enumerate{
#'   \item El archivo de confrontas administrativas consolidado
#'     (\code{registros_con_pui_activos}), que combina PUI + confrontas
#'     manuales + defunciones.
#'   \item El RNPDNO (\code{comprimido}): actualiza
#'     \code{indicadora_indicio_de_vida_localizados} para las personas ya
#'     localizadas que solo tenían coincidencia en PUI,
#'     \code{sub_clasificacion} para las que siguen desaparecidas y solo
#'     tienen coincidencia en PUI, e \code{indicadora_indicio_de_vida} en
#'     función de la \code{sub_clasificacion} resultante.
#' }
#'
#' Si \code{coincidencias_admin_con_inactivas} es \code{NULL}, la función
#' descarga automáticamente el ZIP más reciente de coincidencias
#' administrativas desde Google Drive (con
#' \code{descarga_y_extrae_csv_desde_zip()}), lo lee con
#' \code{leer_csv_pui()} y limpia las carpetas de actualizaciones viejas con
#' \code{limpiar_actualizaciones_viejas_pui()}.
#'
#' @param registros data.frame. Confrontas manuales del RNPDNO. Debe incluir,
#'   al menos, las columnas \code{fub}, \code{indicadora_indicio_de_vida},
#'   \code{institucion_indicadora_de_vida}, \code{numero_instituciones} y
#'   \code{curp_victima}.
#' @param defunciones_df data.frame. Defunciones a incorporar como registros
#'   con indicio de vida administrativo. Debe incluir, al menos, \code{fub} y
#'   \code{tipo_defuncion_institucion}.
#' @param comprimido data.frame. Base del RNPDNO ya procesada (debe incluir,
#'   al menos, \code{fub}, \code{clasificacion_des}, \code{sub_clasificacion},
#'   \code{indicadora_indicio_de_vida_localizados},
#'   \code{indicadora_indicio_de_vida} y \code{fecha_hechos_modificada}). Es
#'   la base que se actualiza y se regresa como \code{comprimido_actualizado}.
#' @param coincidencias_admin_con_inactivas data.frame o \code{NULL}. Reporte
#'   de coincidencias administrativas de la PUI (activas e inactivas), con
#'   columnas como \code{institucion_id}, \code{fub}, \code{curp},
#'   \code{fase_busqueda}, \code{tipo_evento}, \code{is_valid}, etc. Si es
#'   \code{NULL} (por defecto), se descarga automáticamente desde Google Drive.
#' @param guardar_registros_con_pui Logical. Si \code{TRUE}, guarda
#'   \code{registros_con_pui_activos} como \code{.Rds} en
#'   \code{Confrontas/output/resultados_<ddmmyyyy>/registros_con_pui_activos.Rds}.
#'   Por defecto \code{FALSE}.
#'
#' @return Lista con tres elementos:
#'   \item{comprimido_actualizado}{\code{comprimido} con
#'     \code{indicadora_indicio_de_vida_localizados}, \code{sub_clasificacion}
#'     e \code{indicadora_indicio_de_vida} actualizados según las
#'     coincidencias de la PUI.}
#'   \item{registros_con_pui_activos}{Confrontas administrativas consolidadas
#'     (PUI + manuales + defunciones) de personas con desaparición activa o
#'     sin dato de actividad (\code{NA}, proveniente solo de confrontas
#'     manuales).}
#'   \item{registros_en_pui_no_activos}{Registros con coincidencia solo en
#'     PUI y desaparición inactiva (ya localizados), útiles para dar
#'     seguimiento a quiénes tuvieron indicios de vida en PUI antes de ser
#'     localizados.}
#'
#' @examples
#' \dontrun{
#' resultados <- actualizar_confrontas_de_pui(
#'   registros = registros,
#'   defunciones_df = defunciones_df,
#'   comprimido = comprimido,
#'   coincidencias_admin_con_inactivas = NULL,
#'   guardar_registros_con_pui = TRUE
#' )
#' comprimido <- resultados[["comprimido_actualizado"]]
#' registros_con_pui_activos <- resultados[["registros_con_pui_activos"]]
#' }
#'
#' @export
actualizar_confrontas_de_pui <- function(registros = NULL,
                                          defunciones_df = defunciones_df,
                                          comprimido = NULL,
                                          coincidencias_admin_con_inactivas = NULL, # NULL -> descarga de Drive; "aaaa-mm-dd" -> busca local; data.frame -> se usa tal cual
                                          guardar_registros_con_pui = FALSE
                                     ) {


  if (is.null(registros)) {
    stop("¡Atención! La base de datos 'registros' es NULL. Por favor, proporciona un dataframe válido para continuar.")
  }
  if (is.null(defunciones_df)) {
    stop("¡Atención! La base de datos 'defunciones_df' es NULL. Por favor, proporciona un dataframe válido para continuar.")
  }
  if (is.null(comprimido)) {
    stop("¡Atención! La base de datos 'comprimido' es NULL. Por favor, proporciona un dataframe válido para continuar.")
  }

  if (is.null(coincidencias_admin_con_inactivas)) {

    message("¡Atención! La base de datos 'coincidencias_admin_con_inactivas' es NULL. Se procederá a descargar el archivo de confrontas administrativas desde Google Drive.")

    res_descarga <- descarga_y_extrae_csv_desde_zip(
      ruta_actual = here::here("RNPDNO", "input", "datos_procesados_de_la_pui"),
      nombre_archivo_zip = paste0("reporte_coincidencias_validas_", Sys.Date(), ".zip"),
      id_carpeta = "1BMB5LR9rGImky6KJccM_ENeF4E6_DlPj"
    )

    message("Limpiando carpeta de actualizaciones antiguas de la PUI para conservar solo el archivo más reciente, más próximo a la mitad del mes y más cercano al final del mes\n")
    limpiar_actualizaciones_viejas_pui(fs::path_dir(res_descarga$carpeta_actualizacion))

    coincidencias_admin_con_inactivas <- leer_csv_pui(res_descarga$ruta_csv)

    if (file.exists(res_descarga$ruta_zip)) {
      file.remove(res_descarga$ruta_zip)
    }

  } else if (is.character(coincidencias_admin_con_inactivas) &&
             length(coincidencias_admin_con_inactivas) == 1 &&
             str_detect(coincidencias_admin_con_inactivas, "^\\d{4}-\\d{2}-\\d{2}$")) {

    coincidencias_admin_con_inactivas <- buscar_archivo_por_fecha(
      carpeta = here::here("RNPDNO", "input", "datos_procesados_de_la_pui"),
      fecha   = coincidencias_admin_con_inactivas
    )
  }

  # Si coincidencias_admin_con_inactivas es Nulo o tiene 0 filas parar el proceso y avisar
  if (is.null(coincidencias_admin_con_inactivas) || nrow(coincidencias_admin_con_inactivas) == 0) {
    stop("¡Atención! La base de datos 'coincidencias_admin_con_inactivas' es NULL o tiene 0 filas. Por favor, proporciona un dataframe válido para continuar.")
  }
  
  # Empezamos manipulando coincidencias_admin_con_inactivas
  columnas_esperadas <- c("institucion_id", "institucion", "fase_busqueda", "fub", "curp", "tipo_evento", "fecha_desaparicion", "fecha_evento", "calle", "colonia", "codigo_postal", "direccion", "is_valid", "reporte_created_at", "entidad_federativa", "coincidencia_id")

  # Verificar que todas las columnas esperadas estén presentes en coincidencias_admin_con_inactivas
  faltantes <- setdiff(columnas_esperadas, colnames(coincidencias_admin_con_inactivas))
  if (length(faltantes) > 0) {
    stop(
      paste0(
        "¡Atención! Faltan columnas esperadas en coincidencias administrativas: ",
        paste(faltantes, collapse = ", ")
      )
    )
  } else {
    message("¡Perfecto! El archivo contiene todas las columnas esperadas.\n")
  }
  
  # Explorar datos de "coincidencias_admin_con_inactivas"
  # Si hay valores diferentes a 2 y 3 parar proceso y alertar que son fases de búsqueda no válidas
  if(any(!coincidencias_admin_con_inactivas$fase_busqueda %in% c(2, 3))) {
    stop("¡Atención! Se detectaron fases de búsqueda no válidas en el archivo de coincidencias administrativas. Revisa los datos para identificar la discrepancia.")
  } else {
    message("¡Perfecto! Todas las fases de búsqueda en el archivo de coincidencias administrativas son válidas.\n")
  }

  # Hacer una inspercción rápida de las curps para ver si hay vacíos o curps inválidas. Si es mayor a 0 hacer un warning sino solo un message de que no hay curps vacías.
  if(sum(is.na(coincidencias_admin_con_inactivas$curp)) > 0) {
    warning("¡Atención! Se detectaron curps vacías en la base coincidencias_admin_con_inactivas. Revisa los datos para identificar la discrepancia.")
  } else {
    message("¡Perfecto! No se detectaron curps vacías en la base coincidencias_admin_con_inactivas.\n")
  }

  # Crear variable de FUB (quitar UUID4)
  coincidencias_admin_con_inactivas <- coincidencias_admin_con_inactivas |> 
    rename(fub_uuid = fub) |>
    mutate(fub = str_remove(fub_uuid, "([0-9A-F]-?){32}-?$"))

  coincidencias_admin_con_inactivas <- coincidencias_admin_con_inactivas |> 
    mutate(fub = str_remove(fub, "-$"))

  # Nos aseguramos de eliminar CURPs inválidas (aquellas tales que curp == "AEVA950531HMNLLN09")
  coincidencias_admin_con_inactivas <- coincidencias_admin_con_inactivas |> 
    filter(curp != "AEVA950531HMNLLN09")

  # Renombrar fecha created_at (si está con nombre reporte_created_at o fecha_creacion_reporte)
  nombre_columna_fecha <- intersect(
    names(coincidencias_admin_con_inactivas),
    c("reporte_created_at", "fecha_creacion_reporte")
  )

  if (length(nombre_columna_fecha) == 0) {
    warning("No hay columna con nombre 'reporte_created_at' ni 'fecha_creacion_reporte'.")
  } else {
    message("¡Perfecto! Se encontró la columna de fecha de creación del reporte en coincidencias_admin_con_inactivas y se renombró a 'created_at'.\n")
    coincidencias_admin_con_inactivas <- coincidencias_admin_con_inactivas |> 
      rename(created_at = all_of(nombre_columna_fecha))
  }

  # Actualización al 08 de junio de 2026: Se mantienen coincidencias de RENAPO mientras que no sean actas de nacimiento.
  # Actualización del 21 de abril: no considerar la institución de RENAPO (institucion_id == "0044") a petición de Ale Núñez.
  warning("¡Atención! Se eliminarán las coincidencias administrativas provenientes de la institución RENAPO (institucion_id == '0044') y que sean actas de nacimiento. Revisa los datos para identificar la discrepancia.")
  coincidencias_admin_con_inactivas <- coincidencias_admin_con_inactivas |> 
    filter(!(institucion_id == "0044" & str_detect(tipo_evento, "Tipo de Acto: Nacimiento")))

  # Eliminar registros de RENAPO que muestren este regex en tipo_evento : '|1'
  coincidencias_admin_con_inactivas <- coincidencias_admin_con_inactivas |> 
    filter(!(institucion_id == "0044" & str_detect(tipo_evento, "\\|1")))

  # A tipo_evento hay que pegarle entre paréntesis la institución a la que pertenece
  coincidencias_admin_con_inactivas <- coincidencias_admin_con_inactivas |> 
    mutate(tipo_evento = paste0(tipo_evento, " (", institucion, ")"))
  
  # Agrupar por fub e institución para realizar conteos (tbm se puede agrupar por fub_uuid)
  coincidencias_admin_con_inactivas_agrupado <- coincidencias_admin_con_inactivas |> 
  group_by(fub) |> 
  summarise(
    no_apariciones = n(),
    curp = first(curp),
    is_valid = first(is_valid), # Variable que nos dice si la desaparición sigue activa o no
    instituciones = paste(unique(institucion), collapse = ", "),
    tipo_evento = paste(tipo_evento, collapse = ", "), # Variable de tipo de evento
    no_instituciones = n_distinct(institucion_id),
    fases_busqueda = paste(sort(unique(fase_busqueda)), collapse = ", "),
    instituciones_ids = paste(unique(institucion_id), collapse = ", "),
    fecha_desaparicion = first(fecha_desaparicion),
    fecha_evento = first(fecha_evento), # Fecha de evento del trámite que se detectó en la búsqueda administrativa
    calle = first(calle),
    colonia = first(colonia),
    codigo_postal = first(codigo_postal),
    direccion = first(direccion),
    .groups = "drop"
  ) |> 
    rename(desaparicion_activa = is_valid)

  # Contar trámites repetidos 
  coincidencias_admin_con_inactivas_agrupado <- coincidencias_admin_con_inactivas_agrupado |> 
    mutate(
    tramites_repetidos = map_chr(
      str_split(tipo_evento, ", "),
      function(x) {
        conteos <- table(x)
        paste(as.integer(conteos[unique(x)]), collapse = ", ")
      }
    )
  )

  # Ahora solo mantener trámites únicos
  coincidencias_admin_con_inactivas_agrupado <- coincidencias_admin_con_inactivas_agrupado |> 
    mutate(
      tipo_evento = map_chr(
        str_split(tipo_evento, ", "),
        function(x) {
          unique(x) %>% paste(collapse = ", ")
        }
      )
    )

  # Ver conteos de desapariciones activas e inactivas
  num_desapariciones_activas <- sum(coincidencias_admin_con_inactivas_agrupado$desaparicion_activa == TRUE)

  num_desapariciones_inactivas <- sum(coincidencias_admin_con_inactivas_agrupado$desaparicion_activa == FALSE)

  message("Número de desapariciones activas en PUI es: ",comma(num_desapariciones_activas), "\n")
  message("Número de desapariciones inactivas en PUI es: ",comma(num_desapariciones_inactivas), "\n")

  message("El número de coincidencias únicas en PUI es: ", comma(coincidencias_admin_con_inactivas_agrupado |> nrow()))

  # Comprobar cuáles fubs aparecen en RNPDNO "coincidencias_manuales" (registros)
  coincidencias_admin_con_inactivas_agrupado <- coincidencias_admin_con_inactivas_agrupado |> 
    left_join(registros |> 
      filter(indicadora_indicio_de_vida == "con registro administrativo") |> # Descartamos a aquellos registros previos de la PUI
      mutate(indicadora_manual = "con coincidencia manual") |>
              select(fub , indicadora_indicio_de_vida_manual = indicadora_indicio_de_vida,
                institucion_indicadora_de_vida_manual = institucion_indicadora_de_vida,
                numero_instituciones_rnpdno_manual = numero_instituciones,
              indicadora_manual),
            by = "fub") |> 
    mutate(
      indicadora_manual = ifelse(is.na(indicadora_manual), "sin coincidencia manual", indicadora_manual)
    )
  
  # Separamos aquellos que no tienen coincidencia manual para analizarlos por separado
  coincidencias_admin_unicos_sin_manual_fase1 <- coincidencias_admin_con_inactivas_agrupado |> 
  filter(indicadora_manual == "sin coincidencia manual")
  
  # Añadir match con curp + fecha de desaparición en "coincidencias_manuales" para ver si hay coincidencias que no se hayan detectado con el fub
  registros <- registros |> 
    filter(indicadora_indicio_de_vida == "con registro administrativo") |> 
    left_join(comprimido |> 
     select(fub, fecha_hechos_modificada),
     by = c("fub" = "fub")) |>
      mutate(curp_fecha_desaparicion = if_else(is.na(curp_victima), NA_character_,
    paste0(curp_victima, "_", fecha_hechos_modificada)))

  # Agarrar aquellas que no tienen coincidencia manual y construirmos la misma variable de curp + fecha de desaparición para hacer match
  coincidencias_admin_unicos_sin_manual_fase1 <- coincidencias_admin_unicos_sin_manual_fase1 |> 
    mutate(curp_fecha_desaparicion = if_else(is.na(curp), NA_character_,
    paste0(curp, "_", fecha_desaparicion)))
  
  # Verificar si hay coincidencias en curp + fecha de desaparición entre coincidencias_admin_unicos_sin_manual
  coincidencias_admin_unicos_sin_manual_fase1 <- coincidencias_admin_unicos_sin_manual_fase1 |> 
    mutate(coincidencia_curp_fecha = ifelse(curp_fecha_desaparicion %in% registros$curp_fecha_desaparicion, "Registro en ambas (coincidencias administrativas sin match manual y coincidencias manuales) pero distinta FUB", "Registro solo en coincidencias administrativas sin match manual"))

  # Quitamos aquellos registros que sí coinciden en curp + fecha de desaparición con las coincidencias manuales
  coincidencias_admin_unicos_sin_manual_fase2 <- coincidencias_admin_unicos_sin_manual_fase1 |> 
    filter(coincidencia_curp_fecha == "Registro solo en coincidencias administrativas sin match manual")

  # Obtenemos la base de datos que tuvo coincidencia con confrontas manuales (ya sea por FUB o por curp + fecha de desaparición)
  coincidencias_admin_con_manual <- coincidencias_admin_con_inactivas_agrupado |> 
    filter(indicadora_manual == "con coincidencia manual") |> 
    bind_rows(
      coincidencias_admin_unicos_sin_manual_fase1 |> 
        filter(coincidencia_curp_fecha == "Registro en ambas (coincidencias administrativas sin match manual y coincidencias manuales) pero distinta FUB")
    )
  
  # Anunciamos conteos
  message("El número de coincidencias únicas en PUI sin match con confrontas manuales (por FUB o por curp + fecha de desaparición) es: ", comma(coincidencias_admin_unicos_sin_manual_fase2 |> nrow()), "\n")
  message("El número de coincidencias en PUI que también tienen coincidencias con confrontas manuales (por FUB o por curp + fecha de desaparición) es: ", comma(coincidencias_admin_con_manual |> nrow()), "\n")

  instituciones_unicas <- coincidencias_admin_unicos_sin_manual_fase2 |> 
    select(instituciones) |>
    mutate(institucion_split = str_split(instituciones, ",")) |>
    unnest(institucion_split) |>
    mutate(institucion_split = str_squish(institucion_split)) |>  # quitar espacios extra
    count(institucion_split) |>
    arrange(institucion_split) |> 
    pull(institucion_split) 

  message(
  "Las instituciones únicas que aparecen solamente en las coincidencias con PUI:\n  -",
  paste(instituciones_unicas, collapse = "\n  - "),
  "\n"
   )
  message("El número de instituciones únicas que aparecen solamente en las coincidencias con PUI es: ", length(instituciones_unicas), "\n")
  
  # Limpiamos y solo dejamos abreviaturas de las instituciones:
  coincidencias_admin_unicos_sin_manual_fase2 <- 
  coincidencias_admin_unicos_sin_manual_fase2 |> 
  mutate(instituciones = str_replace_all(instituciones, c(
    "Comisión Nacional del Sistema de Ahorro para el Retiro \\(CONSAR\\)" = "CONSAR",
    "Comunicaciones y Transportes \\(SICT\\)" = "SICT",
    "INSTITUTO MEXICANO DEL SEGURO SOCIAL" = "IMSS-PUI",
    "Instituto Nacional de Migración \\(INM\\)" = "INAMI",
    "Petróleos Mexicanos \\(PEMEX\\)" = "PEMEX",
    "Secretaría de Bienestar \\(SEBIEN\\)" = "SEBIEN",
    "Secretaría de Infraestructura" = "SICT",
    "Secretaría de Relaciones Exteriores \\(SRE\\)" = "SRE",
    "Servicio de Administración Tributaria \\(SAT\\)" = "SAT",
    "Servicios de Salud del Instituto Mexicano del Seguro Social para el Bienestar \\(IMSS-Bienestar\\)" = "IMSS-Bienestar"
  )))

  # Hacer lo mismo con coincidencias_admin_con_manual
  coincidencias_admin_con_manual <- 
  coincidencias_admin_con_manual |>
    mutate(instituciones = str_replace_all(instituciones, c(
    "Comisión Nacional del Sistema de Ahorro para el Retiro \\(CONSAR\\)" = "CONSAR",
    "Comunicaciones y Transportes \\(SICT\\)" = "SICT",
    "INSTITUTO MEXICANO DEL SEGURO SOCIAL" = "IMSS-PUI",
    "Instituto Nacional de Migración \\(INM\\)" = "INAMI",
    "Petróleos Mexicanos \\(PEMEX\\)" = "PEMEX",
    "Secretaría de Bienestar \\(SEBIEN\\)" = "SEBIEN",
    "Secretaría de Infraestructura" = "SICT",
    "Secretaría de Relaciones Exteriores \\(SRE\\)" = "SRE",
    "Servicio de Administración Tributaria \\(SAT\\)" = "SAT",
    "Servicios de Salud del Instituto Mexicano del Seguro Social para el Bienestar \\(IMSS-Bienestar\\)" = "IMSS-Bienestar"
  )))

  # Para practicidad unimos ambas bases, pero primero creamos columna de indicadora en cada una
  coincidencias_admin_unicos_sin_manual_fase2 <- coincidencias_admin_unicos_sin_manual_fase2 |> 
    mutate(indicadora_coincidencia_manual = "solo coincidencia en PUI")
  coincidencias_admin_con_manual <- coincidencias_admin_con_manual |> 
    mutate(indicadora_coincidencia_manual = "coincidencia en PUI y registro manual")

  # Unimos ambas bases
  coincidencias_admin_combinado <- bind_rows(coincidencias_admin_unicos_sin_manual_fase2, coincidencias_admin_con_manual)

  # Descartamos columnas no necesarias
  coincidencias_admin_combinado <- coincidencias_admin_combinado |> 
    select(-c(indicadora_indicio_de_vida_manual, institucion_indicadora_de_vida_manual, numero_instituciones_rnpdno_manual, indicadora_manual, curp_fecha_desaparicion, coincidencia_curp_fecha))

  # Cambiar nombre de la institución indicadora de vida
  coincidencias_admin_combinado <- coincidencias_admin_combinado |> 
    rename(institucion_indicadora_de_vida = instituciones)

  # Crear variable indicadora_indicio_de_vida siguiendo la siguiente regla: si indicadora_coincidencia_manual es "coincidencia en PUI y registro manual" entonces "con registro administrativo", si indicadora_coincidencia_manual es "solo coincidencia en PUI" entonces "con registro administrativo en PUI"
  coincidencias_admin_combinado <- coincidencias_admin_combinado |> 
    mutate(indicadora_indicio_de_vida = case_when(
      indicadora_coincidencia_manual == "coincidencia en PUI y registro manual" ~ "con registro administrativo",
      indicadora_coincidencia_manual == "solo coincidencia en PUI" ~ "con registro administrativo en PUI",
      TRUE ~ NA_character_
    ))

  # Quedarnos con columnas necesarias
  coincidencias_admin_combinado <- coincidencias_admin_combinado |> 
    select(fub,
          curp_victima = curp, 
          indicadora_indicio_de_vida,
          institucion_indicadora_de_vida,
          numero_instituciones = no_instituciones,
          indicadora_coincidencia_manual,
          tipo_tramites = tipo_evento,
          tramites_repetidos,
          desaparicion_activa, # Nos dice si una desaparición sigue activa o no, es decir, si la persona sigue desaparecida o ya se localizó, lo cual es información relevante para el reporte semanal
          fecha_evento # Nos dice la fecha de evento del trámite. Es necesaria considerarla para hacer el reporte semanal, ya que solo debemos considerar aquellos registros de coincidencias administrativas que tengan fecha de evento posterior a la fecha de corte del reporte semanal, es decir, a la fecha del último reporte semanal publicado
        )
  
  # --------------------------------------------------------- #
  # Pegar coincidencias de PUI con registros manuales ------ #
  # --------------------------------------------------------- #

  # 1. Primero pegamos los registros de PUI que están tanto en las confrontas manuales como en PUI
  
  # Solo seleccionar coincidencias manuales, sin PUI
  registros <- registros |> 
      filter(indicadora_indicio_de_vida == "con registro administrativo") # Descartamos a aquellos registros previos de la PUI

  # Dejar solo a los registros que no son defunciones (es decir, aquellos con numero_instituciones > 0)
  registros <- registros |> 
    filter(numero_instituciones > 0)
  
  # Pegamos con coincidencias_admin_combinado, solo aquellos que cumplen indicadora_coincidencia_manual = "coincidencia en PUI y registro manual"
  registros_con_pui <- registros |>
    left_join(coincidencias_admin_combinado |> 
      select(-c(curp_victima, indicadora_indicio_de_vida)) |> 
      rename(
        institucion_indicadora_de_vida_pui = institucion_indicadora_de_vida,
        numero_instituciones_pui = numero_instituciones
      ) |> 
      filter(indicadora_coincidencia_manual == "coincidencia en PUI y registro manual"),
      by = "fub"
    ) 
  
  # Consolidar con paste0, collapse = ", " las instituciones indicadoras de vida de RNPDNO y PUI, y sumar el número de instituciones de RNPDNO y PUI, solo cuando haya coincidencia en ambas (es decir, cuando indicadora_coincidencia_manual == "coincidencia en PUI y registro manual")
  registros_con_pui <- registros_con_pui |>
    select(-curp_fecha_desaparicion) |> 
    mutate(
      institucion_indicadora_de_vida = case_when(
        indicadora_coincidencia_manual == "coincidencia en PUI y registro manual" ~ paste0(institucion_indicadora_de_vida, ", ", institucion_indicadora_de_vida_pui),
        TRUE ~ institucion_indicadora_de_vida
      ),
      numero_instituciones = case_when(
        indicadora_coincidencia_manual == "coincidencia en PUI y registro manual" ~ numero_instituciones + numero_instituciones_pui,
        TRUE ~ numero_instituciones
      )
    ) |> 
    select(-c(institucion_indicadora_de_vida_pui, numero_instituciones_pui))

  # 2. Después pegamos los registros que solo tienen coincidencia en PUI

  # Debemos quedarnos solo con aquellos registros de coincidencias_admin_combinado que tienen indicadora_coincidencia_manual == "solo coincidencia en PUI" e indicar si tienen registro en de FUB en RPNDPNO o no.

  # Debemos seguir la siguiente regla: si no tienen registro de FUB en RNPDNO entonces debemos avisar cuántos no tienen FUB en RNPDNO y descartarlos
  coincidencias_admin_solo_pui <- coincidencias_admin_combinado |>
    filter(indicadora_coincidencia_manual == "solo coincidencia en PUI") |> 
    left_join(comprimido |> select(fub, clasificacion_des) |>
                            mutate(con_fub_en_rnpdno = "con fub en rnpdno"), by = "fub") |> 
    mutate(con_fub_en_rnpdno = ifelse(is.na(con_fub_en_rnpdno), "sin fub en rnpdno", con_fub_en_rnpdno))

  con_fub_en_rnpdno <- sum(coincidencias_admin_solo_pui$con_fub_en_rnpdno == "con fub en rnpdno")
  sin_fub_en_rnpdno <- sum(coincidencias_admin_solo_pui$con_fub_en_rnpdno == "sin fub en rnpdno")

  message("El número de registros con solo coincidencia en PUI que tienen FUB en RNPDNO es: ", comma(con_fub_en_rnpdno), "\n")
  message("El número de registros con solo coincidencia en PUI que NO tienen FUB en RNPDNO es: ", comma(sin_fub_en_rnpdno), "\n")

  # Descartamos aquellos que no tienen FUB en RNPDNO
  message("Descartando los registros con solo coincidencia en PUI que NO tienen FUB en RNPDNO...\n")
  coincidencias_admin_solo_pui <- coincidencias_admin_solo_pui |> 
    filter(con_fub_en_rnpdno == "con fub en rnpdno") |> 
    select(-con_fub_en_rnpdno)

  # Antes de la unión asegurarnos de solo considerar columnas de la intersección
  coincidencias_admin_solo_pui <- coincidencias_admin_solo_pui |> 
    select(-clasificacion_des)

  registros_con_pui <- registros_con_pui |> 
    select(-fecha_hechos_modificada)

  # Hacer un bind_rows
  registros_con_pui <- registros_con_pui |> 
    bind_rows(coincidencias_admin_solo_pui)

  # Consideración importante: en registros_con_pui hay tanto registros de desapariciones activas como no activas (columna de PUI)

  # --------------------------------------------------------- #
  ## Primera modificación en comprimido (RNPDNO): indicadora_indicio_de_vida_localizados de comprimido -----
  # --------------------------------------------------------- #
  
  # Debemos sumar aquellos registros que tienen desaparicion activa falsa (es decir, que ya fueron localizados) y sumarlos a aquellos de indicadora_indicio_de_vida_localizados
  
  registros_en_pui_no_activos <- registros_con_pui |> 
    filter(indicadora_coincidencia_manual == "solo coincidencia en PUI", desaparicion_activa == FALSE) 

  num_registros_en_pui_no_activos <- nrow(registros_en_pui_no_activos)

  message("El número de registros con solo coincidencia en PUI y desaparición inactiva (es decir, que ya se localizaron) es: ", comma(num_registros_en_pui_no_activos), "\n")

  # Pegar con comprimido y obtener clasificacion_des para ver que tbm tengan estatus de localización
  registros_en_pui_no_activos <- registros_en_pui_no_activos |> 
    left_join(comprimido |> select(fub, clasificacion_des), by = "fub")

  # Si tienen marca diferente a "Localizados" avisar
  if(any(registros_en_pui_no_activos$clasificacion_des != "Localizados")) {
    warning("¡Atención! Se detectaron registros con solo coincidencia en PUI y desaparición inactiva que no tienen clasificación de 'Localizados' en RNPDNO. Revisa los datos para identificar la discrepancia.\n")
  } else {
    message("¡Perfecto! Todos los registros con solo coincidencia en PUI y desaparición inactiva tienen clasificación de 'Localizados' en RNPDNO.\n")
  }

  # En comprimido hacemos lo siguiente: si una fub está en registros_en_pui_no_activos entonces indicadora_indicio_de_vida_localizados debe cambiar a "con registro administrativo"
  comprimido <- comprimido |> 
    left_join(registros_en_pui_no_activos |> select(fub) |> mutate(en_pui_no_activos = "en_pui_no_activos"), by = "fub") |> 
    mutate(indicadora_indicio_de_vida_localizados = case_when(
      !is.na(en_pui_no_activos) ~ "con registro administrativo",
      TRUE ~ indicadora_indicio_de_vida_localizados
    )) |> 
    select(-en_pui_no_activos)

  # --------------------------------------------------------- #
  ## Segunda modificación: sub_clasificacion cuando es "Desaparecido con registro administrativo" -----
  # --------------------------------------------------------- #
  
  # Seleccionar solo aquellos registros con desaparición activa (es decir, que siguen desaparecidos) y que solo tienen coincidencia en PUI
  registros_en_pui_activos <- registros_con_pui |> 
    filter(indicadora_coincidencia_manual == "solo coincidencia en PUI", desaparicion_activa == TRUE)

  message("El número de registros con solo coincidencias en PUI y con desaparición activa es: ", comma(nrow(registros_en_pui_activos)), "\n")

  # Verificar que todos tengan clasificación de "Desaparecidos" o "Pendientes" en comprimido
  registros_en_pui_activos <- registros_en_pui_activos |> 
    left_join(comprimido |> select(fub, clasificacion_des), by = "fub") |> 
    filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"))

  if(any(!registros_en_pui_activos$clasificacion_des %in% c("Desaparecidos", "Pendientes"))) {
    warning("¡Atención! Se detectaron registros con solo coincidencia en PUI y desaparición activa que no tienen clasificación de 'Desaparecidos' o 'Pendientes' en RNPDNO. Revisa los datos para identificar la discrepancia.\n")
  } else {
    message("¡Perfecto! Todos los registros con solo coincidencia en PUI y desaparición activa tienen clasificación de 'Desaparecidos' o 'Pendientes' en RNPDNO.\n")
  }

  # Misma lógica que en el caso anterior, si la fub de comprimido está en registros_en_pui_activos entonces sub_clasificacion debe cambiar a "Desaparecido con registro administrativo" sino se mantiene igual
  comprimido <- comprimido |> 
    left_join(registros_en_pui_activos |> select(fub) |> mutate(en_pui_activos = "en_pui_activos"), by = "fub") |> 
    mutate(sub_clasificacion = case_when(
      !is.na(en_pui_activos) & clasificacion_des != "Localizados" ~ "Desaparecido con registro administrativo",
      TRUE ~ sub_clasificacion
    )) |> 
    select(-en_pui_activos)

  # --------------------------------------------------------- #
  ## Defunciones ------ 
  # --------------------------------------------------------- #
  
  ## Cruzamos con comprimido y rescatamos solo aquellos después de 2006
  defunciones_df <- defunciones_df |> 
    left_join(comprimido |> select(fub, curp_victima, clasificacion_des, fecha_hechos_modificada), by = "fub") |> 
    filter(clasificacion_des %in% c("Desaparecidos", "Pendientes")) |>
    filter(fecha_hechos_modificada >= as.Date("2006-01-01"))

  # --------------------------------------------------------- #
  # Resultados: 1. actualización del archivo de confrontas administrativas y 2. actualización del archivo del RNPDNO (comprimido)
  # --------------------------------------------------------- #

  # De registros_con_pui seleccionamos solo aquellos que tienen desaparición activa o tienen valor NA (vienen solo de confrontas manuales estos registros, no de PUI, entonces no sabemos si están activos o no, por lo que los dejamos como NA)
  registros_con_pui_activos <- registros_con_pui |> 
    filter(desaparicion_activa == TRUE | is.na(desaparicion_activa))

  # Nos asegurarnos de quedarnos con los registros marcados como Desaparecidos o Pendientes en comprimido
  registros_con_pui_activos <- registros_con_pui_activos |> 
    left_join(comprimido |> select(fub, clasificacion_des), by = "fub") |> 
    filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"))

  message("El número de registros con coincidencias en PUI y en confrontas manuales que tienen clasificación de 'Desaparecidos' o 'Pendientes' en RNPDNO es: ", comma(nrow(registros_con_pui_activos)), "\n")

  # A registros_con_pui_activos le sumamos resultados de defunciones_df
  # Le añadimos indicadora_de_vida = "con registro administrativo"
  defunciones_df$indicadora_indicio_de_vida <- "con registro administrativo"

  # Renombramos tipo_defuncion_institucion a institucion_indicadora_de_vida
  defunciones_df <- defunciones_df |> 
    rename(institucion_indicadora_de_vida = tipo_defuncion_institucion)

  # A cada valor de institucion_indicadora_de_vida reemplazamos el "_" por " de "
  defunciones_df <- defunciones_df |> 
    mutate(institucion_indicadora_de_vida = str_replace_all(institucion_indicadora_de_vida, "_", " de "))

  # Le añadimos una columna de numero_instituciones un 0 pues en caso de defunciones no nos interesa sumar el número de instituciones, sino solo identificar que hay un registro administrativo de defunción
  defunciones_df$numero_instituciones <- 0

  # Seleccionar solo columnas necesarias para pegar con registros_con_pui_activos
  defunciones_df <- defunciones_df |>
    select(fub, curp_victima, indicadora_indicio_de_vida, institucion_indicadora_de_vida, numero_instituciones, clasificacion_des)

  # Anunciar el número de defunciones que se van a pegar con los registros de PUI
  message("El número de registros de defunciones que se van a pegar con los registros de PUI es: ", comma(nrow(defunciones_df)), "\n")

  # Hacer un bind_rows para pegar registros_con_pui_activos con defunciones_df
  registros_con_pui_activos <- registros_con_pui_activos |> 
    bind_rows(defunciones_df)

  message("El número total de registros con coincidencias administrativas (tanto defunciones como indicios de vida) en PUI y en RNPDNO es: ", comma(nrow(registros_con_pui_activos)), "\n")

  # Eliminar columna de "desaparicion_activa" pues ya no es relevante para el análisis, ya que ahora tenemos tanto registros de desapariciones activas como de defunciones
  registros_con_pui_activos <- registros_con_pui_activos |> 
    select(-desaparicion_activa)

  # Limpiar tipo_tramites
  registros_con_pui_activos <- registros_con_pui_activos |> 
    mutate(
    tipo_tramites = str_replace_all(tipo_tramites, c(
      "Comisión Nacional del Sistema de Ahorro para el Retiro \\(CONSAR\\)" = "CONSAR",
      "Comunicaciones y Transportes \\(SICT\\)" = "SICT",
      "INSTITUTO MEXICANO DEL SEGURO SOCIAL" = "IMSS-PUI",
      "Instituto Nacional de Migración \\(INM\\)" = "INAMI",
      "Petróleos Mexicanos \\(PEMEX\\)" = "PEMEX",
      "Secretaría de Bienestar \\(SEBIEN\\)" = "SEBIEN",
      "Secretaría de Infraestructura" = "SICT",
      "Secretaría de Relaciones Exteriores \\(SRE\\)" = "SRE",
      "Servicio de Administración Tributaria \\(SAT\\)" = "SAT",
      "Servicios de Salud del Instituto Mexicano del Seguro Social para el Bienestar \\(IMSS-Bienestar\\)" = "IMSS-Bienestar"
    ))
  )


  # Siempre regresa registros_con_pui_activos, opcionalmente guarda en disco
  if (guardar_registros_con_pui) {
    # Si no existe carpeta "Confrontas/output/resultados_%d%m%Y" crear
    fecha_carpeta <- today()
    fecha_carpeta <- format(fecha_carpeta, "%d%m%Y")

    if(!dir.exists(here::here("Confrontas", "output", paste0("resultados_", fecha_carpeta)))) {
      dir.create(here::here("Confrontas", "output", paste0("resultados_", fecha_carpeta)))
      message("Carpeta 'resultados_", fecha_carpeta, "' creada en 'Confrontas/output'.\n")
    } else {
      message("¡Ntp! ¡La carpeta 'resultados_", fecha_carpeta, "' ya existe en 'Confrontas/output!'.\n")
    }

    saveRDS(registros_con_pui_activos,
        file = here::here("Confrontas", "output", paste0("resultados_", fecha_carpeta),
                          "registros_con_pui_activos.Rds"))
    message("registros_con_pui_activos guardado en disco.\n")
}
  
  # Debemos actualizar la columna indicadora_indicio_de_vida en 'comprimido' para que refleje correctamente la información de los registros con coincidencias administrativas en PUI y en RNPDNO. La lógica es la siguiente: si sub_clasificacion es "Desaparecido con registro administrativo" entonces indicadora_indicio_de_vida debe ser "con registro administrativo", si sub_clasificacion es "Desaparecido sin coincidencia con registro administrativo" entonces indicadora_indicio_de_vida debe ser "sin registro administrativo", sino se mantiene igual.
  comprimido <- comprimido |>
  mutate(
    indicadora_indicio_de_vida = case_when(
      sub_clasificacion == "Desaparecido con registro administrativo" ~ "con registro administrativo",
      sub_clasificacion == "Desaparecido sin coincidencia con registro administrativo" ~ "sin registro administrativo",
      TRUE ~ indicadora_indicio_de_vida
    )
  )
  
  # Regresar comprimido (ya tiene las modificaciones de indicadora_indicio_de_vida_localizados y sub_clasificacion) y registros_con_pui_activos para que se usen en el reporte semanal
  return(list(comprimido_actualizado = comprimido,
    registros_con_pui_activos = registros_con_pui_activos,
    registros_en_pui_no_activos = registros_en_pui_no_activos)) # Regresamos también los registros que tienen solo coincidencia en PUI y desaparición inactiva para trackear a las personas que ya han sido localizadas y tuvieron indicos de vida en PUI
}
                                    
