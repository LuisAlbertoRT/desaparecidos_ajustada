# ————————————————————————————————————————————————————————— #
# Nombre: Jocelyn Flores Rocha
# Contacto: jocelyn.flores@transformaciondigital.gob.mx
# Script: funciones_recurrentes.R
# Proyecto: Nombre del Proyecto
# Fecha: 2026-09-07
# Propósito: Descripción breve
# ————————————————————————————————————————————————————————— #
# Funciones recurrentes -----
# ————————————————————————————————————————————————————————— #

#' Convertir una columna de fecha proveniente de Excel a Date
#'
#' Convierte valores de fecha que pueden llegar en distintos formatos desde
#' un archivo de Excel: ya como `Date`/`POSIXct`, como número de serie de
#' Excel (numérico, con o sin decimales), como ese mismo número de serie
#' guardado por error como texto, o como fecha de calendario en texto con
#' formato "dd/mm/aaaa" (con o sin hora AM/PM en español, que se descarta
#' por no aportar información real).
#'
#' @param x Vector de fechas en cualquiera de los formatos descritos arriba.
#' @param as_character Si `TRUE` (default), regresa un vector de texto en
#'   formato ISO (`"aaaa-mm-dd"`). Si `FALSE`, regresa un vector `Date`.
#'
#' @return Vector de texto (ISO) o `Date`, según `as_character`.
#'
#' @details Las fechas en texto con formato de calendario se asumen en
#'   orden día/mes/año (`dmy`), consistente con el formato usado en
#'   documentos oficiales en español. Cualquier componente de hora se
#'   descarta sin intentar parsearlo.
#'
#' @examples
#' convertir_fecha_excel(45123)                            # numérico
#' convertir_fecha_excel("45123")                          # texto-numérico
#' convertir_fecha_excel("03/04/1973  12:00:00 a. m.")     # texto con hora
#' convertir_fecha_excel("03/04/1973", as_character = FALSE)  # Date
#'
#' @importFrom janitor excel_numeric_to_date
#' @importFrom lubridate dmy
#' @importFrom stringr str_extract
#' @export
convertir_fecha_excel <- function(x, as_character = TRUE) {

  resultado <- if (inherits(x, "Date") || inherits(x, "POSIXct")) {
    as.Date(x)

  } else if (is.numeric(x)) {
    janitor::excel_numeric_to_date(x)

  } else if (is.character(x)) {
    x <- trimws(x)

    es_serial <- grepl("^[0-9]+\\.?[0-9]*$", x)  # serial de Excel como texto (con o sin decimales)

    out <- as.Date(rep(NA_character_, length(x)))
    out[es_serial] <- janitor::excel_numeric_to_date(as.numeric(x[es_serial]))

    # fecha de calendario en texto, ej. "03/04/1973  12:00:00 a. m." -> nos quedamos solo con la fecha
    resto <- !es_serial & !is.na(x)
    fecha_txt <- stringr::str_extract(x[resto], "^\\d{1,2}/\\d{1,2}/\\d{4}")
    out[resto] <- lubridate::dmy(fecha_txt)

    out

  } else {
    rep(as.Date(NA), length(x))  # tipo inesperado (ej. logical NA) -> NA sin tronar
  }

  if (as_character) as.character(resultado) else resultado
}

# Función para obtener la raíz de los datos
# Útil para llamar a la raíz de los datos de Google Drive
raiz_datos <- function(...) {
  raiz <- Sys.getenv("RNPDNO_data_raiz", unset = here::here())
  file.path(raiz, ...)
}

# ----- Función para limpiar números de teléfono ---- #
clean_telefonos <- function(x) {
  x_chr <- as.character(x)
  empty <- is.na(x_chr) | str_trim(x_chr) == ""
  s <- stri_trans_general(str_to_upper(str_squish(x_chr)), "Latin-ASCII")

  # tokens que deben ser NA (match exacto)
  na_token <- stri_detect_regex(
    s,
    "^(?:0|1|/SD|/ND|SIN INFORMACION|SIN DATO|N/?A|NA|NO|NINGUNO|NINGUNA|\\[NULL\\])$",
    opts_regex = stri_opts_regex(case_insensitive = TRUE)
  )

  res <- rep(NA_character_, length(s))
  idx <- which(!empty & !na_token)

  if (length(idx) > 0) {
    s2 <- s[idx]

    # --- EXTRAER Y NORMALIZAR TAGS DE OPERADORA ---
    carrier_matches <- stri_extract_all_regex(s2, "(?i)\\((AT&T|MOVISTAR|TELCEL)\\)")
    carriers_norm <- lapply(carrier_matches, function(v) {
      if (length(v) == 0 || all(is.na(v))) return(character(0))
      tags <- unique(v)
      sapply(tags, function(tag) {
        inner <- stri_replace_all_regex(tag, "^\\(|\\)$", "")
        inner_up <- toupper(inner)
        if (inner_up == "AT&T") return("(AT&T)")
        if (inner_up == "MOVISTAR") return("(movistar)")
        if (inner_up == "TELCEL") return("(telcel)")
        NA_character_
      }, USE.NAMES = FALSE)
    })

    # quitar las etiquetas de operadora del texto
    s2 <- stri_replace_all_regex(s2, "(?i)\\((?:AT&T|MOVISTAR|TELCEL)\\)", "")

    # 1) unir grupos intra-número (ej. 86-82-59 -> 868259)
    s2 <- stri_replace_all_regex(s2, "(?<=\\d)[\\.\\-\\/]+(?=\\d)", "")

    # 2) conjunciones entre dígitos -> coma
    s2 <- stri_replace_all_regex(
      s2,
      "(?<=\\d)\\s*(?:Y|E)\\s*(?=\\d)",
      ",",
      opts_regex = stri_opts_regex(case_insensitive = TRUE)
    )

    # 3) otros separadores (| ;) -> coma
    s2 <- stri_replace_all_regex(s2, "[\\|;]+", ",")

    # 4) mantener solo dígitos y comas; normalizar comas
    s2 <- stri_replace_all_regex(s2, "[^0-9,]", "")
    s2 <- stri_replace_all_regex(s2, ",{2,}", ",")
    s2 <- stri_replace_all_regex(s2, "^,|,$", "")

    # 5) dividir por coma para obtener fragmentos
    parts_list <- stri_split_fixed(s2, ",", simplify = FALSE)

    # 6) procesar cada lista de fragmentos
    res_idx <- vapply(seq_along(parts_list), function(i) {
      parts <- parts_list[[i]]
      parts <- parts[parts != ""]
      if (length(parts) == 0) return(NA_character_)

      # quitar fragmentos que sean solo ceros
      parts <- parts[!stri_detect_regex(parts, "^0+$")]
      if (length(parts) == 0) return(NA_character_)

      lens <- nchar(parts)
      
      # NUEVA REGLA: eliminar números con más de 10 dígitos
      parts <- parts[lens <= 10]
      if (length(parts) == 0) return(NA_character_)
      
      # Recalcular longitudes después del filtro
      lens <- nchar(parts)

      # Si hay más de 1 fragmento y TODOS son cortos (<7), concatenar y validar
      if (length(parts) > 1 && all(lens < 7)) {
        joined <- paste0(parts, collapse = "")
        if (stri_detect_regex(joined, "^0+$")) return(NA_character_)
        if (nchar(joined) >= 7 && nchar(joined) <= 10) {  # validar también aquí
          out_num <- joined
        } else {
          return(NA_character_)
        }
      } else {
        # Conservar solo fragmentos con longitud >= 10
        keep <- parts[lens >= 10]
        if (length(keep) == 0) return(NA_character_)
        out_num <- paste(keep, collapse = ", ")
      }

      # añadir tags de operadora si existen
      carriers <- carriers_norm[[i]]
      if (length(carriers) > 0) {
        paste0(out_num, " ", paste(unique(carriers), collapse = ", "))
      } else {
        out_num
      }
    }, FUN.VALUE = character(1), USE.NAMES = FALSE)

    res[idx] <- res_idx
  }

  # preservar NA para vacíos y tokens explícitos
  res[empty | na_token] <- NA_character_
  res
}

# ------ Función para ejecutar un script de Python como proceso externo y recuperar el archivo que genera ---- #
#' Ejecuta un script de Python como proceso externo y recupera el archivo que genera
#'
#' Alternativa a `reticulate` para llamar código de Python desde R: en vez de
#' correr Python "dentro" de la sesión de R, lo corre como un proceso aparte
#' (`system2()`), pasándole un archivo de entrada (típicamente un csv) y
#' esperando que el script escriba un archivo de salida (típicamente una
#' imagen) en la ruta indicada. Es el equivalente "por fuera" de un
#' `source()`, ya que R y Python no comparten sesión ni objetos: todo lo que
#' cruza la frontera tiene que pasar por disco (archivos) o por argumentos de
#' línea de comandos.
#'
#' @param script_python Ruta al script .py a ejecutar. Debe aceptar como
#'   argumentos posicionales, en este orden: la ruta de `archivo_entrada`
#'   (si no es `NULL`) y la ruta del archivo de salida (se genera
#'   automáticamente con `tempfile()`).
#' @param archivo_entrada Ruta a un archivo que el script de Python debe leer
#'   (p. ej. un csv con `readr::write_csv()`), o `NULL` si el script no
#'   necesita datos de entrada.
#' @param args_extra Vector de argumentos adicionales que se le pasan al
#'   script después de las rutas de entrada/salida (p. ej. parámetros de
#'   estilo, título, etc.).
#' @param extension_salida Extensión del archivo que el script debe producir
#'   (sin punto), p. ej. `"png"`. Default `"png"`.
#' @param python_bin Ruta o nombre del intérprete de Python a usar. Default
#'   toma la variable de entorno `RNPDNO_python_bin` si existe (mismo patrón
#'   que usas para `RNPDNO_data_raiz` en tu `.Renviron`), y si no, usa
#'   `"python3"`. Útil si tu función vive en un venv/conda específico y no en
#'   el Python del PATH.
#'
#' @return Ruta (character) del archivo de salida generado por Python.
#'
#' @examples
#' \dontrun{
#' graficar_con_python(
#'   script_python = "scripts/mi_grafica.py",
#'   archivo_entrada = "datos_temp.csv"
#' )
#' }
graficar_con_python <- function(script_python,
                                 archivo_entrada = NULL,
                                 args_extra = character(0),
                                 extension_salida = "png",
                                 python_bin = Sys.getenv("RNPDNO_python_bin", unset = "python3")) {

  if (!file.exists(script_python)) {
    stop("No encontré el script de Python en: ", script_python)
  }

  archivo_salida <- tempfile(fileext = paste0(".", extension_salida))

  args <- c(
    shQuote(script_python),
    if (!is.null(archivo_entrada)) shQuote(archivo_entrada),
    shQuote(archivo_salida),
    args_extra
  )

  salida_consola <- system2(python_bin, args = args, stdout = TRUE, stderr = TRUE)
  estatus <- attr(salida_consola, "status")

  if (!is.null(estatus) && estatus != 0) {
    stop(
      "El script de Python (", script_python, ") falló:\n",
      paste(salida_consola, collapse = "\n")
    )
  }

  if (!file.exists(archivo_salida)) {
    stop(
      "El script de Python corrió pero no generó el archivo esperado (",
      archivo_salida, "). Salida de consola:\n",
      paste(salida_consola, collapse = "\n")
    )
  }

  archivo_salida
}