# Ejecutar con Rscript "notebooks en R/tests/test_banci.R".
# Prueba el script autónomo con datos sintéticos, sin insumos reales.

necesarios <- c("openxlsx", "arrow", "lubridate")
faltantes <- necesarios[!vapply(necesarios, requireNamespace, logical(1), quietly = TRUE)]
if (length(faltantes)) stop("Instala los paquetes de prueba: ", paste(faltantes, collapse = ", "))

argumento <- grep("^--file=", commandArgs(), value = TRUE)
if (length(argumento) != 1L) stop("Ejecuta esta prueba con Rscript.")
prueba <- normalizePath(sub("^--file=", "", argumento))
script <- file.path(dirname(dirname(prueba)), "2_Procesamiento_ETL_BANCI.R")
rscript <- file.path(R.home("bin"), "Rscript")
entrada <- tempfile(fileext = ".xlsx")
salida <- tempfile(fileext = ".parquet")
on.exit(unlink(c(entrada, salida)), add = TRUE)

anio <- lubridate::year(Sys.Date()) + 2L
while (!lubridate::leap_year(anio)) anio <- anio + 1L
futura <- as.Date(sprintf("%04d-02-29", anio))
base <- data.frame(
  ENTIDAD = "JALISCO", LLAVE = "TEST", ID_CI = "99", NTRA_CI = "000",
  FHA_DE_INI = as.Date("2025-01-01"), FHA_DE_HCHOS = futura,
  NOM_MUN_HCHOS = "GUADALAJARA", ID_MUN_HCHOS = "1", DELITO_HOM = "NO",
  SEXO = "HOMBRE", FHA_NAC = as.Date("2000-01-01"), FOLIO_RNPDNO = "ABC",
  FUB_OK = "OTRO", PRIMER_APELLIDO = NA_character_, SEGUNDO_APELLIDO = NA_character_,
  NOMBRES = "JUAN DE LA CRUZ PEREZ", CURP = "AAAA800101HDFAAA01",
  LOCALIZADO_O_NO_LOCALIZADO = "NO LOCALIZADO", FUE_DELITO = "NO"
)
openxlsx::write.xlsx(list(Victimas = base), entrada)

ejecutar <- function(...) {
  resultado <- suppressWarnings(system2(rscript, shQuote(c(script, ...)),
                                       stdout = TRUE, stderr = TRUE))
  estado <- attr(resultado, "status")
  list(estado = if (is.null(estado)) 0L else estado, mensajes = resultado)
}

resultado <- ejecutar(entrada, salida, "Victimas", "TRUE")
if (resultado$estado != 0L) stop(paste(resultado$mensajes, collapse = "\n"))
tabla <- arrow::read_parquet(salida)
stopifnot(
  nrow(tabla) == 1L,
  tabla$fub_ok_banci == "OTRO",
  tabla$nombres_derivada_banci == "JUAN",
  tabla$primer_apellido_derivada_banci == "DE LA CRUZ",
  tabla$segundo_apellido_derivada_banci == "PEREZ",
  tabla$id_carpeta_derivada_banci == "JALISCO/99",
  tabla$curp_valida_derivada_banci,
  as.Date(tabla$fha_de_hchos_derivada_banci) <= Sys.Date(),
  !is.null(arrow::read_parquet(salida, as_data_frame = FALSE)$schema$metadata$banci_resumen)
)

# Un corte anterior debe fallar sin tocar el resultado ya generado.
checksum <- unname(tools::md5sum(salida))
base$FHA_DE_INI <- as.Date("2024-01-01")
openxlsx::write.xlsx(list(Victimas = base), entrada, overwrite = TRUE)
anterior <- ejecutar(entrada, salida, "Victimas", "TRUE")
stopifnot(anterior$estado != 0L, any(grepl("anterior", anterior$mensajes)),
          identical(checksum, unname(tools::md5sum(salida))))

# También se impide sobrescribir el propio Excel de entrada.
mismo_archivo <- ejecutar(entrada, entrada)
stopifnot(mismo_archivo$estado != 0L, any(grepl("sobrescribir", mismo_archivo$mensajes)))
cat("Pruebas BANCI correctas.\n")
