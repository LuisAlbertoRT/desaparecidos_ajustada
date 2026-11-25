# Procesamiento local del RNPDNO.
#
# Ejecución:
# Rscript 1_Procesamiento_ETL_RNPDNO.R <archivo RNPDNO> <carpeta RENAPO> <salida parquet>
# El archivo de entrada puede ser Parquet o un Excel con las tres hojas originales.
# Las rutas son argumentos: este script no depende de la ubicación de otro proyecto.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) {
  stop("Uso: Rscript 1_Procesamiento_ETL_RNPDNO.R <RNPDNO> <carpeta RENAPO> <salida parquet>")
}

paquetes <- c("arrow", "dplyr", "readxl", "readr", "lubridate", "stringr")
faltantes <- paquetes[!vapply(paquetes, requireNamespace, logical(1), quietly = TRUE)]
if (length(faltantes)) stop("Instala los paquetes de R: ", paste(faltantes, collapse = ", "))

entrada <- args[[1]]
carpeta_renapo <- args[[2]]
salida <- args[[3]]
if (!file.exists(entrada)) stop("No existe el archivo RNPDNO: ", entrada)
if (!dir.exists(carpeta_renapo)) stop("No existe la carpeta RENAPO: ", carpeta_renapo)
if (file.exists(salida) &&
    identical(normalizePath(entrada), normalizePath(salida))) {
  stop("La salida no puede sobrescribir el archivo RNPDNO de entrada.")
}

# Se conserva el orden de los cruces: ante varias CURP válidas para un FUB gana
# la primera del primer archivo en que aparece, igual que en el procesamiento.
archivos_renapo <- file.path(carpeta_renapo, c(
  "CURP_act260525.csv", "curps_reconstruidas_210625.xlsx",
  "curps_con_resultado_prueba_01072025.xlsx", "curps_con_resultado_prueba_050825.xlsx"
))
codigos_entidad <- c(
  "AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR",
  "HG", "JC", "MC", "MN", "MS", "NT", "NL", "OC", "PL", "QT", "QR", "SP",
  "SL", "SR", "TC", "TS", "TL", "VZ", "YN", "ZS", "NE"
)
entidades <- c(
  "Aguascalientes", "Baja California", "Baja California Sur", "Campeche",
  "Coahuila", "Colima", "Chiapas", "Chihuahua", "Ciudad de México", "Durango",
  "Guanajuato", "Guerrero", "Hidalgo", "Jalisco", "México", "Michoacán",
  "Morelos", "Nayarit", "Nuevo León", "Oaxaca", "Puebla", "Querétaro",
  "Quintana Roo", "San Luis Potosí", "Sinaloa", "Sonora", "Tabasco",
  "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatán", "Zacatecas",
  "Nacido en el Extranjero"
)

curp_valida <- function(x) {
  x <- as.character(x)
  !is.na(x) & nchar(x) == 18L &
    grepl("^[A-Z]{4}[0-9]{6}[HM]", x, ignore.case = TRUE) &
    grepl("[A-Z]{3}.{2}$", x, ignore.case = TRUE) &
    toupper(substr(x, 12L, 13L)) %in% codigos_entidad
}

normalizar_texto <- function(x) {
  x <- toupper(as.character(x))
  x <- chartr("ÁÉÍÓÚÜ", "AEIOUU", x)
  stringr::str_squish(x)
}

normalizar_nombres <- function(tabla) {
  nombres <- tolower(trimws(names(tabla)))
  nombres <- gsub("\\.", "", gsub(" ", "_", nombres, fixed = TRUE))
  nombres[nombres == "curp_victima"] <- "curp_vic"
  nombres[nombres %in% c("expediente", "expedientes")] <- "expedientes"
  if (anyDuplicated(nombres)) stop("Hay columnas repetidas después de normalizar los nombres.")
  names(tabla) <- nombres
  tabla
}

como_texto <- function(tabla) {
  # Estos literales son los nulos de los archivos fuente, no valores de identidad.
  nulos <- c("", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN",
             "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>", "N/A", "NA",
             "NULL", "NaN", "None", "n/a", "nan", "null")
  tabla[] <- lapply(tabla, function(x) {
    x <- as.character(x)
    x[x %in% nulos] <- NA_character_
    x
  })
  tabla
}

extension <- tolower(tools::file_ext(entrada))
if (extension == "parquet") {
  fuente <- como_texto(normalizar_nombres(as.data.frame(arrow::read_parquet(entrada))))
  if (!all(c("estatus", "conidentidad") %in% names(fuente))) {
    stop("El Parquet debe tener estatus y conidentidad para reconstruir las hojas.")
  }
  localizada <- fuente$estatus %in% c("LOCALIZADA CON VIDA", "LOCALIZADA SIN VIDA")
  identidad <- tolower(trimws(fuente$conidentidad)) == "true"
  identidad[is.na(identidad)] <- FALSE
  fuente$hoja <- ifelse(localizada, "LOCALIZADAS",
                        ifelse(identidad, "DESAPARECIDAS", "PENDIENTES"))
} else if (extension == "xlsx") {
  hojas <- c(PENDIENTES = "ACTUALIZACION_PENDIENTE",
             LOCALIZADAS = "LOCALIZADAS", DESAPARECIDAS = "DESAPARECIDAS")
  if (length(setdiff(unname(hojas), readxl::excel_sheets(entrada)))) {
    stop("El Excel debe contener ACTUALIZACION_PENDIENTE, LOCALIZADAS y DESAPARECIDAS.")
  }
  fuente <- dplyr::bind_rows(lapply(names(hojas), function(hoja) {
    tabla <- como_texto(normalizar_nombres(
      as.data.frame(readxl::read_excel(entrada, sheet = hojas[[hoja]], col_types = "text"))
    ))
    tabla$hoja <- hoja
    tabla
  }))
} else {
  stop("Formato no admitido; usa un archivo .parquet o .xlsx.")
}

# Nombres originales de salida, antes de agregar las columnas derivadas.
originales <- c(
  "fub", "estatus", "nombre_vic", "primerapellido_vic", "segundoapellido_vic",
  "sexo", "fechanacimiento", "idestadonacimiento_vic", "idestado", "idmunicipio",
  "fechahechos", "fechapercato", "fechalocaliza", "delitolocalizacion",
  "fechacaptura", "dependencia_origen", "fecha_consulta", "curp_vic", "expedientes"
)
faltantes <- setdiff(originales, names(fuente))
if (length(faltantes)) stop("Faltan columnas RNPDNO: ", paste(faltantes, collapse = ", "))

# Cada hoja se deduplica por FUB después de verificar que sus datos de identidad
# no se contradigan. Los valores ausentes no cuentan como una segunda identidad.
identidad <- c("curp_vic", "nombre_vic", "primerapellido_vic",
               "segundoapellido_vic", "sexo", "idestadonacimiento_vic")
hojas <- split(fuente, factor(fuente$hoja,
                              levels = c("PENDIENTES", "LOCALIZADAS", "DESAPARECIDAS")))
hojas <- lapply(hojas, function(tabla) {
  duplicadas <- tabla[duplicated(tabla$fub) | duplicated(tabla$fub, fromLast = TRUE), ]
  if (nrow(duplicadas)) {
    conflictos <- duplicadas |>
      dplyr::filter(!is.na(.data$fub)) |>
      dplyr::group_by(.data$fub) |>
      dplyr::summarise(dplyr::across(dplyr::all_of(identidad),
                                     ~ dplyr::n_distinct(.x, na.rm = TRUE)),
                       .groups = "drop")
    if (any(as.matrix(conflictos[identidad]) > 1L)) {
      stop("Hay FUB duplicados con datos de identidad contradictorios.")
    }
  }
  tabla[!duplicated(tabla$fub), , drop = FALSE]
})

# Consolidar cruces RENAPO sin alterar la CURP original del RNPDNO.
renapo <- lapply(archivos_renapo, function(archivo) {
  if (!file.exists(archivo)) {
    warning("No se encontró el cruce RENAPO: ", archivo)
    return(NULL)
  }
  datos <- if (tolower(tools::file_ext(archivo)) == "csv") {
    readr::read_csv(archivo, col_types = readr::cols(.default = "c"), show_col_types = FALSE)
  } else {
    readxl::read_excel(archivo, col_types = "text")
  }
  nombres <- tolower(names(datos))
  fub <- which(grepl("fub", nombres, fixed = TRUE))[1]
  curp <- which(grepl("curp", nombres, fixed = TRUE))[1]
  if (is.na(fub) || is.na(curp)) stop("El cruce no contiene columnas FUB y CURP: ", archivo)
  datos <- data.frame(fub = as.character(datos[[fub]]), curp = as.character(datos[[curp]]))
  datos[curp_valida(datos$curp), , drop = FALSE]
})
renapo <- dplyr::bind_rows(renapo)
if (!nrow(renapo)) {
  renapo <- data.frame(fub = character(), curp = character())
  warning("No se encontraron CURP válidas en los cruces RENAPO.")
}
renapo <- renapo[!duplicated(renapo$fub), , drop = FALSE]

fecha <- function(x) {
  # Las fechas derivadas se interpretan en UTC para que Parquet conserve la zona.
  suppressWarnings(lubridate::parse_date_time(
    x, orders = c("ymd HMS", "ymd HM", "ymd"), tz = "UTC", quiet = TRUE
  ))
}

enriquecer <- function(tabla, imputar) {
  resultado <- tabla[originales]
  names(resultado) <- paste0(originales, "_rnpdno")
  curp <- tabla$curp_vic
  if (imputar) {
    recuperada <- renapo$curp[match(tabla$fub, renapo$fub)]
    cambiar <- !curp_valida(curp) & !is.na(recuperada)
    curp[cambiar] <- recuperada[cambiar]
  }
  for (col in c("fechanacimiento", "fechahechos", "fechapercato",
                "fechalocaliza", "fechacaptura")) {
    resultado[[paste0(col, "_derivada_rnpdno")]] <- fecha(tabla[[col]])
  }
  resultado$idestado_derivada_rnpdno <- suppressWarnings(as.numeric(tabla$idestado))
  resultado$idmunicipio_derivada_rnpdno <- suppressWarnings(as.numeric(tabla$idmunicipio))
  resultado$curp_vic_derivada_rnpdno <- curp
  resultado$curp_vic_valida_derivada_rnpdno <- curp_valida(curp)
  partes <- lapply(tabla[c("nombre_vic", "primerapellido_vic", "segundoapellido_vic")],
                   function(x) ifelse(is.na(x), "", x))
  resultado$nombre_completo_derivada_rnpdno <- normalizar_texto(
    paste(partes[[1]], partes[[2]], partes[[3]])
  )
  resultado$fecha_hechos_modificada_derivada_rnpdno <- dplyr::coalesce(
    resultado$fechahechos_derivada_rnpdno, resultado$fechapercato_derivada_rnpdno,
    resultado$fechacaptura_derivada_rnpdno
  )
  indice_entidad <- match(resultado$idestado_derivada_rnpdno, seq_along(entidades))
  resultado$estado_derivada_rnpdno <- normalizar_texto(entidades[indice_entidad])
  resultado
}

corte <- fecha(fuente$fecha_consulta)
if (all(is.na(corte))) {
  warning("No hay fecha de consulta válida; se usa la fecha actual.")
  corte <- as.POSIXct(Sys.Date(), tz = "UTC")
} else {
  corte <- as.POSIXct(as.Date(max(corte, na.rm = TRUE), tz = "UTC"), tz = "UTC")
}
procesadas <- lapply(hojas, enriquecer, imputar = TRUE)
original_localizadas <- enriquecer(hojas$LOCALIZADAS, imputar = FALSE)
fubs_con_curp <- unique(unlist(lapply(procesadas, function(x) {
  x$fub_rnpdno[x$curp_vic_valida_derivada_rnpdno]
})))

desaparecidos <- list()
pendientes <- list()
for (hoja in c("PENDIENTES", "DESAPARECIDAS")) {
  tabla <- procesadas[[hoja]]
  con <- tabla[tabla$curp_vic_valida_derivada_rnpdno, , drop = FALSE]
  con$clasificacion_des_derivada_rnpdno <- rep("Desaparecidos", nrow(con))
  sin <- tabla[!tabla$fub_rnpdno %in% fubs_con_curp, , drop = FALSE]
  sin$clasificacion_des_derivada_rnpdno <- rep("Pendientes", nrow(sin))
  desaparecidos[[hoja]] <- con
  pendientes[[hoja]] <- sin
}
original_localizadas$clasificacion_des_derivada_rnpdno <- rep("Localizados", nrow(original_localizadas))
resultado <- dplyr::bind_rows(c(unname(desaparecidos), unname(pendientes),
                               list(original_localizadas)))
if (!nrow(resultado)) stop("El resultado RNPDNO está vacío.")
resultado$fecha_consulta_derivada_rnpdno <- corte
derivadas <- c(
  "fechanacimiento", "idestado", "idmunicipio", "fechahechos", "fechapercato",
  "fechalocaliza", "fechacaptura", "fecha_consulta", "curp_vic", "curp_vic_valida",
  "nombre_completo", "fecha_hechos_modificada", "estado", "clasificacion_des"
)
resultado <- resultado[c(paste0(originales, "_rnpdno"),
                         paste0(derivadas, "_derivada_rnpdno"))]
dir.create(dirname(salida), recursive = TRUE, showWarnings = FALSE)
arrow::write_parquet(resultado, salida)
message("Registros exportados: ", nrow(resultado), " → ", salida)
