# Procesamiento local de BANCI.
#
# Ejecución:
# Rscript 2_Procesamiento_ETL_BANCI.R <archivo.xlsx> <salida.parquet> [hoja] [estricto]
#
# La hoja predeterminada es "Victimas". El cuarto argumento puede ser TRUE para
# detener el procesamiento si la entrega no pasa las validaciones de contenido;
# FALSE (predeterminado) muestra los problemas y continúa. Si la salida ya existe,
# se usa como referencia de la entrega anterior antes de reemplazarla.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L || length(args) > 4L) {
  stop("Uso: Rscript 2_Procesamiento_ETL_BANCI.R <archivo.xlsx> <salida.parquet> [hoja] [estricto]")
}
entrada <- args[[1]]
salida <- args[[2]]
hoja <- if (length(args) >= 3L) args[[3]] else "Victimas"
estricto <- if (length(args) >= 4L) toupper(args[[4]]) else "FALSE"
if (!estricto %in% c("TRUE", "FALSE")) stop("El argumento estricto debe ser TRUE o FALSE.")
estricto <- estricto == "TRUE"

paquetes <- c("arrow", "readxl", "lubridate", "stringr", "stringi", "jsonlite")
faltantes <- paquetes[!vapply(paquetes, requireNamespace, logical(1), quietly = TRUE)]
if (length(faltantes)) stop("Instala los paquetes de R: ", paste(faltantes, collapse = ", "))
if (!file.exists(entrada)) stop("No existe el archivo BANCI: ", entrada)
if (tolower(tools::file_ext(entrada)) != "xlsx") stop("La entrada BANCI debe ser un archivo .xlsx.")
if (file.exists(salida) && identical(normalizePath(entrada), normalizePath(salida))) {
  stop("La salida no puede sobrescribir el archivo BANCI de entrada.")
}
if (!hoja %in% readxl::excel_sheets(entrada)) stop("No existe la hoja BANCI: ", hoja)

# Se aceptan las variantes de encabezados que han llegado en distintas entregas.
mapa <- list(
  nombres = c("nombres", "nombre"), primer_apellido = c("primer_apellido", "paterno", "apellido_paterno"),
  segundo_apellido = c("segundo_apellido", "materno", "apellido_materno"),
  curp = c("curp", "curp_victima"), sexo = "sexo",
  fha_nac = c("fha_nac", "fecha_nacimiento", "fecha_nac"),
  entidad = c("entidad", "entidad_federativa", "estado_reporta", "entidad_reporta"),
  id_mun_hchos = c("id_mun_hchos", "idmunicipio_hechos", "id_municipio_hechos"),
  nom_mun_hchos = c("nom_mun_hchos", "municipio_hechos", "nombre_municipio_hechos", "municipio"),
  fha_de_hchos = c("fha_de_hchos", "fecha_hechos", "fecha de hechos"),
  fha_de_ini = c("fha_de_ini", "fecha_inicio", "fecha inicio"),
  localizado_o_no_localizado = c("localizado_o_no_localizado", "estatus", "estatus_localizado"),
  fue_delito = c("fue_delito", "fue_delito_origen"), delito_hom = c("delito_hom", "delito_homologado"),
  llave = "llave", folio_rnpdno = c("folio_rnpdno", "folio_rnpdno_ori", "fub_ok"),
  ntra_ci = c("ntra_ci", "ntraci"), id_ci = c("id_ci", "idci")
)

normalizar_encabezado <- function(x) {
  x <- tolower(stringi::stri_trans_general(trimws(x), "Latin-ASCII"))
  x <- gsub("[[:space:].-]+", "_", x)
  gsub("[^a-z0-9_]", "", x)
}
normalizar_texto <- function(x) {
  x <- chartr("ÁÉÍÓÚÜ", "AEIOUU", toupper(as.character(x)))
  stringr::str_squish(x)
}
normalizar_entidad <- function(x) {
  x <- stringi::stri_trans_general(as.character(x), "Latin-ASCII")
  stringr::str_squish(toupper(x))
}

# Leer cada celda según su tipo evita perder fechas o números cuando una misma
# columna mezcla texto y celdas numéricas, como ocurre con FHA_NAC e ID_CI.
datos <- readxl::read_excel(entrada, sheet = hoja, col_types = "list",
                            trim_ws = FALSE, .name_repair = "minimal")
if (!nrow(datos)) stop("El archivo BANCI no trae registros.")
nombres <- normalizar_encabezado(names(datos))
if (anyDuplicated(nombres)) stop("Hay encabezados duplicados después de normalizarlos.")
names(datos) <- nombres
for (destino in names(mapa)) {
  if (destino %in% names(datos)) next
  opciones <- normalizar_encabezado(mapa[[destino]])
  origen <- opciones[opciones %in% names(datos)][1]
  if (!is.na(origen)) names(datos)[match(origen, names(datos))] <- destino
}
opcionales <- c("fue_delito", "delito_hom", "nom_mun_hchos", "id_ci")
requeridas <- setdiff(names(mapa), opcionales)
faltantes <- setdiff(requeridas, names(datos))
if (length(faltantes)) stop("Faltan columnas obligatorias: ", paste(faltantes, collapse = ", "))
for (nombre in setdiff(opcionales, names(datos))) {
  warning("Columna opcional ausente: ", nombre)
  datos[[nombre]] <- rep(list(NA), nrow(datos))
}

celda_texto <- function(x) {
  if (!length(x) || is.na(x)) return(NA_character_)
  if (inherits(x, "POSIXt")) return(format(x, "%Y-%m-%d %H:%M:%S", tz = "UTC"))
  if (is.logical(x)) return(if (x) "True" else "False")
  if (is.numeric(x)) return(format(x, scientific = FALSE, trim = TRUE))
  x <- gsub("\r\n", "\n", as.character(x), fixed = TRUE)
  if (x %in% c("", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN",
               "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>", "N/A", "NA",
               "NULL", "NaN", "None", "n/a", "nan", "null")) NA_character_ else x
}
texto_columna <- function(columna) {
  vapply(columna, celda_texto, character(1))
}
texto <- lapply(datos[names(mapa)], texto_columna)
tipo_celda <- function(columna, prueba) {
  presentes <- vapply(columna, function(x) length(x) > 0L && !is.na(x), logical(1))
  any(presentes) && all(vapply(columna[presentes], prueba, logical(1)))
}

fecha <- function(x) {
  # Las fechas de Excel se leen como celdas de fecha o texto; el resultado es UTC
  # para que la escritura sin zona horaria preserve el mismo instante en Parquet.
  suppressWarnings(lubridate::parse_date_time(
    x, orders = c("ymd HMS", "ymd HM", "ymd", "dmy HMS", "dmy"),
    tz = "UTC", quiet = TRUE
  ))
}
fecha_validacion <- function(x) {
  f <- fecha(x)
  numero <- suppressWarnings(as.numeric(x))
  serial <- !is.na(numero) & numero >= 1 & numero <= 100000 & is.na(f)
  f[serial] <- as.POSIXct(as.Date(numero[serial], origin = "1899-12-30"), tz = "UTC")
  f
}

estados <- c(
  "Aguascalientes", "Baja California", "Baja California Sur", "Campeche",
  "Coahuila", "Colima", "Chiapas", "Chihuahua", "Ciudad de México", "Durango",
  "Guanajuato", "Guerrero", "Hidalgo", "Jalisco", "México", "Michoacán",
  "Morelos", "Nayarit", "Nuevo León", "Oaxaca", "Puebla", "Querétaro",
  "Quintana Roo", "San Luis Potosí", "Sinaloa", "Sonora", "Tabasco",
  "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatán", "Zacatecas",
  "Nacido en el Extranjero"
)
claves_estado <- stats::setNames(seq_along(estados), normalizar_entidad(estados))
claves_estado <- c(claves_estado, "ESTADO DE MEXICO" = 15, "EDOMEX" = 15,
                   "DISTRITO FEDERAL" = 9, "CDMX" = 9, "COAHUILA DE ZARAGOZA" = 5,
                   "MICHOACAN DE OCAMPO" = 16, "VERACRUZ DE IGNACIO DE LA LLAVE" = 30)

resumir <- function(entidad, inicio, archivo) {
  fechas <- fecha_validacion(inicio)
  fechas[!is.na(fechas) & fechas > as.POSIXct(Sys.Date(), tz = "UTC")] <- NA
  clave <- unname(claves_estado[normalizar_entidad(entidad)])
  frecuencias <- table(clave, useNA = "no")
  list(
    archivo = basename(archivo), procesado = format(Sys.time(), "%Y-%m-%dT%H:%M:%S"),
    filas = length(entidad),
    fecha_corte = if (all(is.na(fechas))) NULL else format(max(fechas, na.rm = TRUE), "%Y-%m-%d", tz = "UTC"),
    fecha_inicio_min = if (all(is.na(fechas))) NULL else format(min(fechas, na.rm = TRUE), "%Y-%m-%d", tz = "UTC"),
    por_entidad = as.list(stats::setNames(as.integer(frecuencias), names(frecuencias)))
  )
}

# Comparar con el resumen guardado en el Parquet anterior; si no existe el
# metadato, reconstruirlo a partir de las columnas originales de esa salida.
referencia <- NULL
if (file.exists(salida)) {
  anterior <- arrow::read_parquet(salida, as_data_frame = FALSE)
  meta <- anterior$schema$metadata
  if (!is.null(meta$banci_resumen)) {
    referencia <- jsonlite::fromJSON(meta$banci_resumen, simplifyVector = FALSE)
  } else {
    anterior <- as.data.frame(anterior)
    if (!all(c("entidad_banci", "fha_de_ini_banci") %in% names(anterior))) {
      stop("La salida anterior no tiene las columnas necesarias para compararla.")
    }
    referencia <- resumir(anterior$entidad_banci, anterior$fha_de_ini_banci, salida)
  }
}

resumen <- resumir(texto$entidad, texto$fha_de_ini, entrada)
errores <- character()
avisos <- character()
agregar_error <- function(x) errores <<- c(errores, x)
agregar_aviso <- function(x) avisos <<- c(avisos, x)
if (!resumen$filas) agregar_error("El archivo no trae registros.")
inicio <- fecha_validacion(texto$fha_de_ini)
futuras <- !is.na(inicio) & inicio > as.POSIXct(Sys.Date(), tz = "UTC")
if (any(futuras)) agregar_aviso(paste(sum(futuras), "fechas de inicio posteriores a hoy."))
if (is.null(resumen$fecha_corte)) {
  agregar_error("No hay una fecha de inicio válida para determinar el corte.")
} else if (any(is.na(inicio))) {
  agregar_aviso(paste(sum(is.na(inicio)), "registros sin fecha de inicio legible."))
}
estatus <- normalizar_entidad(texto$localizado_o_no_localizado)
if (any(is.na(estatus) | !grepl("^(NO )?LOCALIZAD[AO]S?$", estatus))) {
  agregar_error(paste(sum(is.na(estatus) | !grepl("^(NO )?LOCALIZAD[AO]S?$", estatus)),
                      "registros tienen un estatus de localización no reconocido."))
}
entidad <- normalizar_entidad(texto$entidad)
if (any(is.na(claves_estado[entidad]))) {
  agregar_error(paste(sum(is.na(claves_estado[entidad])), "registros tienen entidad no reconocida."))
}
sexo <- normalizar_entidad(texto$sexo)
sexo_nuevo <- !is.na(sexo) & nzchar(sexo) &
  !sexo %in% c("HOMBRE", "MUJER", "SE DESCONOCE", "NO ESPECIFICA", "NO ESPECIFICADO")
if (any(sexo_nuevo)) agregar_aviso(paste(sum(sexo_nuevo), "registros tienen categorías de sexo nuevas."))
sin_llave <- is.na(texto$llave) | trimws(texto$llave) == ""
if (length(sin_llave) && mean(sin_llave) > 0.05) {
  agregar_error(paste(sum(sin_llave), "registros sin LLAVE; exceden el 5%."))
} else if (any(sin_llave)) {
  agregar_aviso(paste(sum(sin_llave), "registros sin LLAVE."))
}
if (!is.null(resumen$fecha_corte)) {
  hechos <- fecha_validacion(texto$fha_de_hchos)
  posteriores <- !is.na(hechos) & hechos > as.POSIXct(resumen$fecha_corte, tz = "UTC")
  if (any(posteriores)) agregar_aviso(paste(sum(posteriores), "fechas de hechos posteriores al corte."))
}
if (!is.null(referencia) && !is.null(referencia$fecha_corte) && !is.null(resumen$fecha_corte)) {
  ant <- as.Date(referencia$fecha_corte)
  nuevo <- as.Date(resumen$fecha_corte)
  n_ant <- as.integer(referencia$filas)
  if (nuevo < ant) {
    agregar_error(paste("La entrega es anterior a la salida existente:", nuevo, "<", ant))
  } else if (nuevo == ant && resumen$filas != n_ant) {
    agregar_aviso(paste("Mismo corte con diferencia de", resumen$filas - n_ant, "registros."))
  } else if (nuevo > ant) {
    if (resumen$filas <= n_ant) agregar_error("El nuevo corte no creció respecto al anterior.")
    if (n_ant > 0 && resumen$filas / n_ant - 1 > 0.50) agregar_aviso("El nuevo corte creció más del 50%.")
    meses <- (lubridate::year(nuevo) - lubridate::year(ant)) * 12 +
      lubridate::month(nuevo) - lubridate::month(ant)
    if (meses > 1) agregar_aviso(paste("Hay", meses, "meses entre ambas entregas."))
    if (!identical(resumen$fecha_inicio_min, referencia$fecha_inicio_min)) {
      agregar_aviso("Cambió la fecha de inicio más antigua de la entrega.")
    }
    for (clave in names(referencia$por_entidad)) {
      n <- as.integer(referencia$por_entidad[[clave]])
      m <- resumen$por_entidad[[clave]]
      if (is.null(m)) m <- 0L
      if (m == 0L && n >= 10L) agregar_error(paste("La entidad", clave, "desapareció de la entrega."))
      else if (n - m >= 10L && (n - m) / n > 0.05) {
        agregar_aviso(paste("La entidad", clave, "perdió más del 5% de registros."))
      }
    }
  }
}
message("BANCI: ", resumen$filas, " registros; corte: ", resumen$fecha_corte)
if (length(avisos)) warning(paste(avisos, collapse = "\n"))
if (length(errores)) {
  mensaje <- paste(c("La entrega no pasó las validaciones:", errores), collapse = "\n")
  if (estricto) stop(mensaje) else warning(mensaje)
}

# Separar nombres completos cuando falta algún apellido; se conservan aparte las
# columnas originales, ya que las reparaciones solo afectan las derivadas.
reparar_nombre <- function(nombre, primero, segundo) {
  if (is.na(nombre) || (!is.na(primero) && !is.na(segundo)) || !nzchar(nombre)) {
    return(c(nombre, primero, segundo))
  }
  nombre_limpio <- stringr::str_squish(nombre)
  patron <- stringr::regex("\\b(de\\s+la|de\\s+las|de\\s+los|de|del|la|las|los|y)\\s+",
                           ignore_case = TRUE)
  protegido <- stringr::str_replace_all(nombre_limpio, patron, function(x) gsub(" ", "_", x, fixed = TRUE))
  partes <- strsplit(protegido, " ", fixed = TRUE)[[1]]
  partes <- partes[nzchar(partes)]
  n <- length(partes)
  if (n >= 3L) {
    valores <- c(paste(partes[seq_len(n - 2L)], collapse = " "), partes[n - 1L], partes[n])
  } else if (n == 2L) {
    valores <- c(partes[1], partes[2], NA_character_)
  } else {
    valores <- c(nombre, NA_character_, NA_character_)
  }
  gsub("_", " ", valores, fixed = TRUE)
}
reparados <- t(vapply(seq_len(nrow(datos)), function(i) {
  reparar_nombre(texto$nombres[i], texto$primer_apellido[i], texto$segundo_apellido[i])
}, character(3)))
reparados[reparados == "0"] <- NA_character_

codigos_curp <- c("AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG",
                  "GT", "GR", "HG", "JC", "MC", "MN", "MS", "NT", "NL", "OC",
                  "PL", "QT", "QR", "SP", "SL", "SR", "TC", "TS", "TL", "VZ",
                  "YN", "ZS", "NE")
curp <- toupper(gsub("\\s+", "", texto$curp))
curp_valida <- !is.na(curp) & nchar(curp) == 18L &
  grepl("^[A-Z]{4}[0-9]{6}[HM]", curp, ignore.case = TRUE) &
  grepl("[A-Z]{3}.{2}$", curp, ignore.case = TRUE) &
  substr(curp, 12L, 13L) %in% codigos_curp

# Las fechas de hechos futuras se corrigen retrocediendo años, no días. El operador
# %m-% resuelve el 29 de febrero como 28 de febrero cuando el año no es bisiesto.
hechos <- fecha(texto$fha_de_hchos)
limite <- as.POSIXct(Sys.Date(), tz = "UTC")
while (any(!is.na(hechos) & hechos > limite)) {
  futuras <- !is.na(hechos) & hechos > limite
  hechos[futuras] <- lubridate::`%m-%`(hechos[futuras], lubridate::years(1))
}

originales <- c("entidad", "llave", "id_ci", "ntra_ci", "fha_de_ini", "fha_de_hchos",
                "nom_mun_hchos", "id_mun_hchos", "delito_hom", "sexo", "fha_nac",
                "folio_rnpdno", "primer_apellido", "segundo_apellido", "nombres", "curp",
                "localizado_o_no_localizado", "fue_delito")
resultado <- as.data.frame(texto[originales], optional = TRUE, stringsAsFactors = FALSE)
names(resultado) <- paste0(originales, "_banci")
resultado$fha_de_ini_banci <- fecha(texto$fha_de_ini)
resultado$fha_de_hchos_banci <- fecha(texto$fha_de_hchos)
if (tipo_celda(datos$fha_nac, function(x) inherits(x, "POSIXt"))) {
  resultado$fha_nac_banci <- fecha(texto$fha_nac)
}
resultado$fub_ok_banci <- if ("fub_ok" %in% names(datos)) {
  if (all(vapply(datos$fub_ok, function(x) is.na(x) || is.numeric(x), logical(1)))) {
    vapply(datos$fub_ok, function(x) if (is.na(x)) NA_real_ else as.numeric(x), numeric(1))
  } else texto_columna(datos$fub_ok)
} else texto$folio_rnpdno
resultado$entidad_derivada_banci <- normalizar_texto(texto$entidad)
resultado$id_ci_derivada_banci <- stringr::str_trim(texto$id_ci)
resultado$ntra_ci_derivada_banci <- stringr::str_trim(texto$ntra_ci)
resultado$id_ci_derivada_banci[resultado$id_ci_derivada_banci == ""] <- NA_character_
resultado$ntra_ci_derivada_banci[resultado$ntra_ci_derivada_banci == ""] <- NA_character_
resultado$fha_de_hchos_derivada_banci <- hechos
resultado$nom_mun_hchos_derivada_banci <- normalizar_texto(texto$nom_mun_hchos)
resultado$localizado_o_no_localizado_derivada_banci <- toupper(stringr::str_trim(texto$localizado_o_no_localizado))
resultado$fha_nac_derivada_banci <- fecha(texto$fha_nac)
resultado$nombres_derivada_banci <- reparados[, 1]
resultado$primer_apellido_derivada_banci <- reparados[, 2]
resultado$segundo_apellido_derivada_banci <- reparados[, 3]
partes <- lapply(seq_len(3L), function(i) ifelse(is.na(reparados[, i]), "", reparados[, i]))
resultado$nombre_completo_derivada_banci <- normalizar_texto(paste(partes[[1]], partes[[2]], partes[[3]]))
resultado$curp_valida_derivada_banci <- curp_valida
carpeta <- ifelse(is.na(resultado$ntra_ci_derivada_banci), "", resultado$ntra_ci_derivada_banci)
id <- ifelse(is.na(resultado$id_ci_derivada_banci), "", resultado$id_ci_derivada_banci)
parte <- normalizar_texto(ifelse(!nzchar(carpeta) | grepl("^0+$", carpeta), id, carpeta))
resultado$id_carpeta_derivada_banci <- ifelse(
  nzchar(trimws(parte)) & !is.na(resultado$entidad_derivada_banci),
  paste0(resultado$entidad_derivada_banci, "/", parte), NA_character_
)

# Mantener los tipos y el resumen del corte en el Parquet, para que la siguiente
# ejecución pueda detectar entregas anteriores o pérdidas de registros.
tabla <- arrow::Table$create(resultado)
schema <- tabla$schema
tipos <- lapply(seq_along(schema$fields), function(i) {
  campo <- schema$fields[[i]]
  if (inherits(resultado[[campo$name]], "POSIXt")) {
    arrow::field(campo$name, arrow::timestamp("us"))
  } else if (is.character(resultado[[campo$name]])) {
    arrow::field(campo$name, arrow::large_utf8())
  } else campo
})
tabla <- tabla$cast(do.call(arrow::schema, tipos))
tabla <- tabla$ReplaceSchemaMetadata(list(
  banci_resumen = as.character(jsonlite::toJSON(resumen, auto_unbox = TRUE, null = "null"))
))
dir.create(dirname(salida), recursive = TRUE, showWarnings = FALSE)
arrow::write_parquet(tabla, salida)
message("Registros exportados: ", nrow(resultado), " → ", salida)
