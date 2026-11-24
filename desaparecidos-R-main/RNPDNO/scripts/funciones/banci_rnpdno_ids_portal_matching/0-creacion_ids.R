# —————————————————————————————————————————————————————————————————————————————
#
# Proyecto:       Desaparecidos - Cruce BANCI-RNPDNO
#
# Script:         scripts/0-creacion_ids.R
# Objetivo:       Crear identificadores homologados en RNPDNO y BANCI:
#                 - id_persona:  identifica a la persona (CURP + nombre completo
#                                `+ sexo + fecha y entidad de nacimiento). Usa
#                                los mismos componentes y la misma limpieza en
#                                ambas bases, por lo que es comparable entre
#                                ellas y sirve para el cruce.
#                 - id_carpeta:  identifica la carpeta/expediente de
#                                investigación.
#                 - id_registro: identifica de forma única cada registro de
#                                cada base; sirve para deduplicar y dar
#                                seguimiento a registros individuales.
#
#                 Reglas de diseño:
#                 - Sin llave "postiza": sin CURP válida y sin nombre completo
#                   (nombre + primer apellido), el id_persona queda en NA de
#                   forma intencional; se reporta, no se imputa.
#                 - CURP válida = 18+ caracteres alfanuméricos tras limpieza;
#                   si no, NA.
#                 - Apellidos con placeholders ("NNN", "XXX", "X", "N") se
#                   tratan como NA.
#                 - Todos los hashes se calculan con openssl::sha1().
#                 - Solo se eliminan duplicados de id_registro exactos
#                   (idénticos en todas las columnas); duplicados con contenido
#                   distinto detienen la ejecución.
#
# Autor:          Jorge A. Gómez
# Correo(s):      jorge.gomez@transformaciondigital.gob.mx
#
# Fecha:          20/07/2026
#
# Última
# actualización:  23/07/2026
#
# —————————————————————————————————————————————————————————————————————————————
# PREAMBULO
# —————————————————————————————————————————————————————————————————————————————


# Limpiar entorno de trabajo
# rm(list = ls())       # Limpiar entorno de trabajo
# source("~/.Rprofile") # Cargar configuraciones globales
# cat("\014")           # Limpiar consola


# Carga de paquetes
pacman::p_load(tidyverse, readxl, writexl, janitor, lubridate, jsonlite, fst,
    openxlsx, scales, glue, DBI, RPostgres, duckdb, openssl, stringi)

# Cargar dotenv
# dotenv::load_dot_env(".env")


# —————————————————————————————————————————————————————————————————————————————
# CODIGO
# —————————————————————————————————————————————————————————————————————————————


# —————————————————————————————————————————————————————————————————————————————
# FUNCIONES
# —————————————————————————————————————————————————————————————————————————————
# source("./scripts/0-funciones.R")

# Llamar de forma implícita a la carpeta 
# glob con "*" busca toda dirección con cola anterior a "utils/funciones_cat_geo_inegi.R"
archivo <- dir_ls(here::here(), recurse = TRUE, glob = "*utils/funciones_cat_geo_inegi.R")
source(archivo)


#' Limpiar componentes de texto para identificadores
#' @descripcion Normaliza texto para usarlo como componente de un identificador:
#' quita todos los espacios, pasa a minúsculas, translitera a Latin-ASCII (sin
#' acentos) y convierte cadenas vacías a NA. Así "Pérez  Gómez" y "PEREZ GOMEZ"
#' producen exactamente el mismo componente.
#' @param x Vector de texto.
#' @return Vector de texto normalizado (NA si quedó vacío).
limpiar_texto_id <- function(x) {
    x |>
        str_remove_all("\\s") |>
        str_to_lower() |>
        stri_trans_general("Latin-ASCII") |>
        na_if("")
}

# Placeholders que aparecen en el lugar de un apellido pero no identifican a
# nadie (ya normalizados: minúsculas, sin espacios). Se comparan DESPUÉS de
# limpiar_texto_id(), por lo que cubren variantes como "NnN" o "N N N"
placeholders_apellido <- c("nnn", "xxx", "x", "n")

#' Limpiar apellidos para identificadores
#' @descripcion Igual que limpiar_texto_id(), pero además trata los
#' placeholders de apellido ("NNN", "XXX", "X", "N", en cualquier combinación
#' de mayúsculas/minúsculas, con o sin espacios) como NA: no son apellidos reales
#' y, de usarse, contaminarían el id_persona y le darían identificador a
#' registros que no tienen nombre suficiente. Se usa en ambas bases para que
#' el id_persona siga siendo comparable entre ellas.
#' @param x Vector de texto con apellidos.
#' @return Vector normalizado (NA si quedó vacío o si era un placeholder).
limpiar_apellido <- function(x) {
    x <- limpiar_texto_id(x)
    if_else(x %in% placeholders_apellido, NA_character_, x)
}

#' Limpiar CURP para identificadores
#' @descripcion Estandariza la CURP: pasa a mayúsculas ANTES de filtrar
#' caracteres (una CURP capturada en minúsculas no debe perder sus letras),
#' elimina todo lo que no sea A-Z/0-9 y descarta (NA) las CURPs con menos de
#' 18 caracteres, que son inválidas por construcción y solo meterían ruido
#' al identificador.
#' @param x Vector de texto con CURPs crudas.
#' @return Vector con CURPs válidas de 18+ caracteres o NA.
limpiar_curp <- function(x) {
    x <- x |> str_to_upper() |> str_remove_all("[^0-9A-Z]")
    if_else(str_length(x) < 18, NA_character_, x)
}

#' Limpiar sexo para identificadores
#' @descripcion Normaliza la variable de sexo (sin espacios, minúsculas) y
#' convierte a NA los valores tipo "Se desconoce" o vacíos, para que un
#' "desconocido" no aporte información falsa al identificador.
#' @param x Vector de texto con el sexo.
#' @return Vector normalizado o NA.
limpiar_sexo <- function(x) {
    x |>
        str_remove_all("\\s") |>
        str_to_lower() |>
        na_if("sedesconoce") |>
        na_if("")
}

#' Verificar y deduplicar por id_registro
#' @descripcion Verifica que todos los registros que comparten un mismo
#' id_registro sean idénticos en TODAS sus columnas comparadas (duplicados
#' exactos), excluyendo 'indicador' de la comparación porque puede diferir
#' entre duplicados legítimos. Si lo son, elimina los duplicados conservando
#' la primera aparición e informa cuántos se eliminaron.
#'
#' Antes de esa comparación general, resuelve un caso especial: si dentro de
#' un id_registro duplicado todas las columnas coinciden EXCEPTO las del
#' "paquete de localización" (localizado_o_no_localizado y su '_ori',
#' con_o_sin_vida y su '_ori', fecha_localizacion y su '_ori', voluntaria y
#' su '_ori', fue_delito y su '_ori', delito y su '_ori', observaciones y su
#' '_ori', fecha_ultimo_contacto, hora_ultimo_contacto), y al menos una fila
#' del grupo tiene localizado_o_no_localizado == "LOCALIZADA", se interpreta
#' como el mismo registro actualizado a "Localizada": se conserva una sola
#' fila del grupo (la primera, sin importar si es la que dice "Localizada")
#' y se descartan las demás.
#'
#' Si tras esa resolución persisten id_registro duplicados con contenido
#' distinto en las columnas comparadas, se abre un browser() interactivo
#' (para inspeccionar el caso antes de detener la ejecución) y luego DETIENE
#' la ejecución (stop) indicando las columnas inconsistentes y cuántos
#' id_registro están afectados: eso indica que el id_registro no está
#' diferenciando bien los registros y hay que revisar los datos o el diseño
#' del identificador antes de continuar.
#' @param df Data frame con columna id_registro (sin valores NA).
#' @param nombre_base Nombre de la base (solo para los mensajes).
#' @return Data frame deduplicado.
verificar_deduplicar_id_registro <- function(df, nombre_base = "base") {

    if (!"id_registro" %in% names(df)) {
        stop("El data.frame de ", nombre_base, " no tiene columna 'id_registro'.")
    }
    if (any(is.na(df$id_registro))) {
        stop("Hay registros con id_registro vacío en ", nombre_base,
             ". Revisar los insumos con los que se construye el identificador.")
    }

    # Columnas a comparar: todas menos el propio id_registro e 'indicador'.
    # 'indicador' se excluye porque puede diferir entre duplicados legítimos
    # y no forma parte de la identidad del registro
    columnas_comparar <- setdiff(names(df), c("id_registro", "indicador"))

    n_duplicados <- sum(duplicated(df$id_registro))

    # Sin duplicados: nada que hacer
    if (n_duplicados == 0) {
        message(">> ", nombre_base, ": todos los id_registro son únicos (",
                nrow(df), " registros).")
        return(df)
    }

    # Duplicados que son el mismo registro actualizado a "Localizada": cuando
    # dentro de un id_registro duplicado las ÚNICAS columnas que difieren son
    # las del "paquete" de localización (estatus y los datos que se llenan
    # junto con él: cómo/cuándo se localizó, si fue con vida, si fue
    # voluntario, si hubo delito, y sus versiones '_ori'; todas las demás
    # columnas comparadas coinciden), se trata del mismo registro pero con el
    # estatus actualizado; se conserva la fila "Localizada" completa (por eso
    # no importa cuál de estas columnas haya cambiado) y se descartan las demás
    columnas_paquete_localizacion <- intersect(
        c("localizado_o_no_localizado", "localizado_o_no_localizado_ori",
          "con_o_sin_vida", "con_o_sin_vida_ori",
          "fecha_localizacion", "fecha_localizacion_ori",
          "voluntaria", "voluntaria_ori",
          "fue_delito", "fue_delito_ori",
          "delito", "delito_ori",
          "observaciones", "observaciones_ori",
          "fecha_ultimo_contacto", "hora_ultimo_contacto"),
        columnas_comparar
    )

    if ("localizado_o_no_localizado" %in% columnas_paquete_localizacion) {

        columnas_comparar_sin_loc <- setdiff(columnas_comparar, columnas_paquete_localizacion)

        ids_resueltos_localizada <- df |>
            group_by(id_registro) |>
            filter(n() > 1) |>
            summarise(
                across(all_of(columnas_comparar_sin_loc), ~ n_distinct(.x) == 1),
                tiene_localizada = any(str_to_upper(localizado_o_no_localizado) == "LOCALIZADA"),
                .groups = "drop"
            ) |>
            filter(if_all(all_of(columnas_comparar_sin_loc)), tiene_localizada) |>
            pull(id_registro)

        if (length(ids_resueltos_localizada) > 0) {
            message(">> ", nombre_base, ": ", length(ids_resueltos_localizada), " id_registro ",
                    "duplicados corresponden al mismo registro con al menos una fila 'Localizada'; ",
                    "se conserva una sola fila (cualquiera) y se descartan las demás.")

            df <- df |>
                group_by(id_registro) |>
                filter(!(id_registro %in% ids_resueltos_localizada) | row_number() == 1) |>
                ungroup()
        }
    }

    # Recalcular duplicados tras resolver el caso de "Localizada"
    n_duplicados <- sum(duplicated(df$id_registro))

    if (n_duplicados == 0) {
        message(">> ", nombre_base, ": todos los id_registro son únicos tras resolver ",
                "duplicados por actualización a 'Localizada' (", nrow(df), " registros).")
        return(df)
    }

    # Columnas (de las comparadas) donde algún grupo duplicado difiere
    columnas_inconsistentes <- df |>
        group_by(id_registro) |>
        filter(n() > 1) |>
        summarise(across(all_of(columnas_comparar), ~ n_distinct(.x) == 1),
                  .groups = "drop") |>
        select(-id_registro) |>
        select(where(~ any(!.x))) |>
        names()

    # Duplicados con contenido distinto: detener la ejecución con los detalles
    if (length(columnas_inconsistentes) > 0) {
        ids_inconsistentes <- df |>
            group_by(id_registro) |>
            filter(n() > 1) |>
            summarise(across(all_of(columnas_inconsistentes), ~ n_distinct(.x) > 1),
                      .groups = "drop") |>
            filter(if_any(all_of(columnas_inconsistentes))) |>
            nrow()

        browser()

        stop("En ", nombre_base, " hay ", ids_inconsistentes, " id_registro ",
             "duplicados con valores diferentes en: ",
             paste(columnas_inconsistentes, collapse = ", "),
             ". El id_registro no está diferenciando bien los registros; ",
             "revisar los datos o el diseño del identificador antes de continuar.")
    }

    # Duplicados que coinciden en todas las columnas comparadas: eliminar
    # conservando la primera aparición ('indicador' puede diferir; sobrevive
    # el de la primera fila)
    message(">> ", nombre_base, ": los id_registro duplicados coinciden en ",
            "todas las columnas comparadas (excepto posiblemente 'indicador'). ",
            "Se eliminan ", n_duplicados, " registros duplicados.")
    df |> distinct(id_registro, .keep_all = TRUE)
}

#' Reportar cobertura de identificadores
#' @descripcion Informa cuántos registros quedaron sin id_carpeta (warning:
#' indica insumos de carpeta/expediente no utilizables que conviene revisar) y
#' cuántos sin id_persona (message: es el comportamiento esperado por diseño
#' cuando no hay CURP válida ni nombre completo; se reporta el porcentaje para
#' monitorear su magnitud). Regresa el data frame sin modificarlo, por lo que
#' puede usarse dentro de un pipe.
#' @param df Data frame con columnas id_persona e id_carpeta.
#' @param nombre_base Nombre de la base (solo para los mensajes).
#' @return El mismo data frame, sin cambios.
reportar_cobertura_ids <- function(df, nombre_base = "base") {

    n_sin_carpeta <- sum(is.na(df$id_carpeta))
    if (n_sin_carpeta > 0) {
        warning(">> ", nombre_base, ": ", n_sin_carpeta, " registros (",
                round(100 * n_sin_carpeta / nrow(df), 2), "% de la base) sin ",
                "id_carpeta: no tienen expediente/número de carpeta utilizable ",
                "o falta la entidad. Revisar los insumos.")
    } else {
        message(">> ", nombre_base, ": todos los registros tienen id_carpeta.")
    }

    n_sin_persona <- sum(is.na(df$id_persona))
    if (n_sin_persona > 0) {
        message(">> ", nombre_base, ": ", n_sin_persona, " registros (",
                round(100 * n_sin_persona / nrow(df), 2), "% de la base) sin ",
                "id_persona: no cuentan con CURP válida ni nombre completo, ",
                "se quedan en NA de forma intencional.")
    } else {
        message(">> ", nombre_base, ": todos los registros tienen id_persona.")
    }

    df
}





# —————————————————————————————————————————————————————————————————————————————
# DATA
# —————————————————————————————————————————————————————————————————————————————

# Insumo 0: Catálogo de entidades
# Si no se suministra entonces llamar a la función get_geo_inegi() para que se llame desde el servidor a la base
cat_ent <- get_geo_inegi("entidades") |> select(CVE_ENT, entidad = NOM_ENT) |> clean_names()

# Catálogo extendido para claves numéricas: asegurar cve de 2 dígitos e incluir 33 = Extranjero
cat_ent_ext <- cat_ent |>
    filter(!cve_ent == "33") |> 
    mutate(cve_ent = cve_ent |> str_pad(side = "left", pad = "0", width = 2)) |>
    add_row(cve_ent = "33", entidad = "Extranjero")

# # Insumo 1: RNPDNO
# rnpdno_raw <- read_xlsx("input/raw/20260719/RNPDNO_procesado_20072026.xlsx") |> clean_names()

# # Insumo 2: BANCI
# banci_raw <- read_xlsx("input/raw/20260719/BANCI_202606_desap_caracteristicas.xlsx") |> clean_names()



# VALIDACIONES DE INSUMOS
# —————————————————————————————————————————————————————————————————————————————
# Los identificadores dependen de que existan ciertas columnas y de que los
# insumos mínimos del id_registro (fub en RNPDNO, llave en BANCI) nunca estén
# vacíos. Se valida ANTES de procesar para fallar temprano y con mensajes claros.

# Columnas requeridas para construir los identificadores de cada base
columnas_requeridas_rnpdno <- c(
    # Identificación de la persona
    "curp_victima", "nombre_vic", "primerapellido_vic", "segundoapellido_vic",
    "sexo", "fechanacimiento", "idestadonacimiento_vic",
    # Carpeta de investigación
    "dependencia_origen", "expediente",
    # Registro
    "fub"
)

columnas_requeridas_banci <- c(
    # Identificación de la persona
    "curp", "nombres", "primer_apellido", "segundo_apellido", "sexo",
    "fha_nac", "entidad_nacimiento",
    # Carpeta de investigación
    "entidad_reporta", "ntra_ci", "id_ci",
    # Registro: llave + columnas que diferencian registros cuando no se
    # cuenta con nombre ni CURP
    "llave", "municipio_visto", "lugar_ultimo_contacto", "id_vicf", "pob",
    "disc", "edad", "nacional", "folio_rnpdno"
)

if (!all(columnas_requeridas_rnpdno %in% names(rnpdno_raw))) {
    stop("¡Faltan columnas requeridas en RNPDNO: ",
         paste(setdiff(columnas_requeridas_rnpdno, names(rnpdno_raw)), collapse = ", "))
}

if (!all(columnas_requeridas_banci %in% names(banci_raw))) {
    stop("¡Faltan columnas requeridas en BANCI: ",
         paste(setdiff(columnas_requeridas_banci, names(banci_raw)), collapse = ", "))
}

# fub y llave son el insumo mínimo del id_registro de cada base: si alguno está
# vacío hay un error en los datos y no se puede continuar
if (any(is.na(rnpdno_raw$fub))) {
    stop("¡Atención! Hay registros con fub vacío en RNPDNO. No se puede continuar ",
         "dado que el fub es el insumo del id_registro. Revisar los datos.")
}

if (any(is.na(banci_raw$llave))) {
    stop("¡Atención! Hay registros con llave vacía en BANCI. No se puede continuar ",
         "dado que la llave es el insumo del id_registro. Revisar los datos.")
}

# Apellidos con placeholders ("NNN", "XXX", "X"): no identifican a la persona,
# por lo que al construir el id_persona se tratan como NA (ver
# limpiar_apellido()). Aquí solo se reporta cuántos registros los traen para
# dimensionar el problema
n_placeholder_rnpdno <- sum(
    limpiar_texto_id(rnpdno_raw$primerapellido_vic) %in% placeholders_apellido |
        limpiar_texto_id(rnpdno_raw$segundoapellido_vic) %in% placeholders_apellido
)
if (n_placeholder_rnpdno > 0) {
    warning("¡Atención! Hay ", n_placeholder_rnpdno, " registros en RNPDNO con un ",
            "placeholder (", paste(str_to_upper(placeholders_apellido), collapse = ", "),
            ") en alguno de los apellidos. Se tratarán como NA en los identificadores.")
}

n_placeholder_banci <- sum(
    limpiar_texto_id(banci_raw$primer_apellido) %in% placeholders_apellido |
        limpiar_texto_id(banci_raw$segundo_apellido) %in% placeholders_apellido
)
if (n_placeholder_banci > 0) {
    warning("¡Atención! Hay ", n_placeholder_banci, " registros en BANCI con un ",
            "placeholder (", paste(str_to_upper(placeholders_apellido), collapse = ", "),
            ") en alguno de los apellidos. Se tratarán como NA en los identificadores.")
}




# SCRIPT
# —————————————————————————————————————————————————————————————————————————————

# Crear catálogo de fiscalías/dependencias de origen de Expedientes/Carpetas
# Este catálogo es para las fiscalías o entidades de carpetas de investigación
# en el RNPDNO.
cat_fiscalias <- rnpdno_raw |> distinct(dependencia_origen) |>
    transmute(
        dependencia_origen,
        id_dependencia_origen = dependencia_origen |> str_squish() |> str_to_lower() |> stri_trans_general("Latin-ASCII") |> openssl::sha1() |> str_sub(1L, 8L)
    )


# PROCESAMIENTO RNPDNO
# —————————————————————————————————————————————————————————————————————————————
comprimido <- comprimido |>

    # Agregar nombres de entidades con cat_ent_ext (claves numéricas, 33 = Extranjero)
    mutate(
        cve_ent_nac = idestadonacimiento_vic |> str_pad(side = "left", pad = "0", width = 2)
    ) |>
    # Unir nombres: entidad de nacimiento de la víctima
    left_join(cat_ent_ext |> rename(estadonacimiento_vic = entidad), by = c("cve_ent_nac" = "cve_ent")) |> 
    mutate(
        estadonacimiento_vic = coalesce(estadonacimiento_vic, cve_ent_nac),
        estado = coalesce(estado_desaparicion, cve_estado_desaparicion)
    ) |>
    # Reubicar junto a sus claves y tirar temporales
    relocate(estadonacimiento_vic, .after = idestadonacimiento_vic) |>
    relocate(estado, .after = cve_estado_desaparicion) |>
    select(-cve_ent_nac) |>

    mutate(

        # ID PERSONA: hash SHA-1 de CURP + nombre completo + sexo + fecha de
        # nacimiento + entidad de nacimiento (clave INEGI de 2 dígitos), todos
        # normalizados. Ambas bases usan exactamente los mismos componentes y
        # la misma limpieza, de modo que una misma persona produce el mismo
        # hash en RNPDNO y en BANCI y el cruce puede hacerse por id_persona.
        id_persona = paste0(
            coalesce(limpiar_curp(curp_victima), ""),
            coalesce(limpiar_texto_id(nombre_vic), ""),
            coalesce(limpiar_apellido(primerapellido_vic), ""),
            coalesce(limpiar_apellido(segundoapellido_vic), ""),
            coalesce(limpiar_sexo(sexo), ""),
            coalesce(as.character(fechanacimiento |> as.Date()), ""),
            coalesce(idestadonacimiento_vic |> str_pad(side = "left", pad = "0", width = 2), "")
        ) |> openssl::sha1() |> as.character(),

        # Sin CURP y sin nombre suficiente (nombre + primer apellido) no hay
        # forma de identificar a la persona: el id_persona se anula para no
        # colapsar registros de personas distintas en un mismo identificador
        id_persona = if_else(
            is.na(limpiar_curp(curp_victima)) &
                (is.na(limpiar_texto_id(nombre_vic)) | is.na(limpiar_apellido(primerapellido_vic))),
            NA_character_,
            id_persona
        ),

        # ID CARPETA: dependencia de origen (hash corto de 8 caracteres, mismo
        # que en cat_fiscalias) + "/" + número de expediente limpio

        # Normalizar el expediente y quitar los patrones basura. Después se limpian los separadores que
        id_carpeta = expediente |>
            stri_trans_general("Latin-ASCII") |>
            str_to_upper() |>
            str_squish() |>
            str_remove_all(regex(
                str_c("(?:", c( "^S/D$", "SECUESTROS"), ")", collapse = "|"),
                ignore_case = TRUE
            )) |>
            # str_replace_all("/{2,}", "/") |>
            # str_remove_all("^[\\s/.,;:-]+|[\\s/.,;:-]+$") |>
            str_squish(),

        # Descartar los expedientes que quedan con 3 caracteres o menos: son
        # demasiado cortos para identificar una carpeta y solo colapsarían
        # carpetas distintas en un mismo id_carpeta
        id_carpeta = if_else(str_length(id_carpeta) < 4L, NA_character_, id_carpeta),

        # Anteponer la dependencia de origen; sin expediente válido no hay
        # carpeta que identificar y el id_carpeta se queda en NA
        id_carpeta = if_else(
            is.na(id_carpeta),
            NA_character_,
            paste0(
                coalesce(dependencia_origen |> str_squish() |> str_to_lower() |> stri_trans_general("Latin-ASCII") |> openssl::sha1() |> str_sub(1L, 8L), ""),
                "/",
                id_carpeta
            )
        ),

        # ID REGISTRO: hash SHA-1 del fub (folio único de búsqueda) sin
        # espacios. El fub identifica cada registro dentro del RNPDNO
        # (validado arriba: nunca es NA)
        id_registro = fub |> str_remove_all("\\s") |> openssl::sha1() |> as.character()
    ) |>

    # Verificar duplicados de id_registro y eliminar solo los duplicados exactos
    verificar_deduplicar_id_registro(nombre_base = "RNPDNO") |>

    # Reportar registros sin id_carpeta (revisar) y sin id_persona (por diseño)
    reportar_cobertura_ids(nombre_base = "RNPDNO")

# —————————————————————————————————————————————————————————————————————————————

# Contar id_perssona_sha1 únicos
num_id_persona_sha1_unicos <- rnpdno |> 
  filter(!is.na(id_persona)) |> 
  distinct(id_persona) |>
  nrow()

# Contar id_carpeta_sha1 únicos
num_id_carpeta_sha1_unicos <- rnpdno |> 
  filter(!is.na(id_carpeta)) |> 
  distinct(id_carpeta) |>
  nrow()

# Contar id_registro_sha1 únicos
num_id_registro_sha1_unicos <- rnpdno |> 
  filter(!is.na(id_registro)) |> 
  distinct(id_registro) |>
  nrow()

cat("El número único de registros es: ", comma(num_id_registro_sha1_unicos), "\n")
             
comprimido_sin_interseccion <- rnpdno |> 
  filter(origen_categoria_union == "Solo RNPDNO, sin intersección")

num_comprimido_sin_interseccion <- comprimido_sin_interseccion |> 
  nrow()

cat("Número de registros en comprimido_sin_interseccion:", comma(num_comprimido_sin_interseccion), "\n")

## Escoger columnas de interés y renombrarlas para exportar a Excel
comprimido_sin_interseccion <- comprimido_sin_interseccion |> 
  select(
    estado_desaparicion_rnpdno = estado_desaparicion,
    municipio_desaparicion_rnpdno = municipio_desaparicion,
    carpeta_investigacion_rnpdno = expediente,

    fecha_hechos_rnpdno = fechahechos,
    fecha_hechos_modificada_rnpdno = fecha_hechos_modificada,

    # Datos de la persona desaparecida
    fub_rnpdno = fub,
    sexo_rnpdno = sexo,
    fecha_nacimiento_rnpdno = fechanacimiento,
    nombre_vic_rnpdno = nombre_vic,
    primerapellido_vic_rnpdno = primerapellido_vic,
    segundoapellido_vic_rnpdno = segundoapellido_vic,
    curp_victima_rnpdno = curp_victima,
    clasificacion_des_rnpdno = clasificacion_des,

    id_persona,
    id_carpeta,
    id_registro
  )

# Con arrow descargarlo como parquet
library(arrow)

write_parquet(comprimido_sin_interseccion, here::here("RNPDNO",
             "output",
             "cruces_banci_rnpdno",
             "cruces_banci_rnpdno_28072026",
             "comprimido_sin_interseccion_28072026.parquet"))


# PROCESAMIENTO BANCI
# —————————————————————————————————————————————————————————————————————————————

# Eliminar duplicados

# Solo no localizados
subeR_no_localizados <- subeR |> filter(localizado_o_no_localizado == "No localizada")

subeR <- subeR |>

    # ENTIDAD FEDERATIVA (del registro): homologar el nombre contra el
    # catálogo INEGI vía llave de matching (acepta variantes y abreviaturas)
    crear_llave_matching("entidad_reporta") |>
    # Unir con catálogo de entidades
    left_join(cat_ent |> crear_llave_matching("entidad"), by = "LLAVE_ENT") |>
    # Coalescer nombres de entidades
    # TODO: pasar un str_to_title() con cautela
    mutate(
        entidad_reporta = coalesce(entidad, str_to_title(entidad_reporta), NA)
    ) |>
    # Tirar temporales y reubicar
    select(-LLAVE_ENT, -entidad) |>
    relocate(cve_ent, .before = entidad_reporta) |>

    # ENTIDAD DE NACIMIENTO: obtener la clave INEGI de 2 dígitos (33 =
    # Extranjero) para usarla como componente del id_persona, igual que en
    # RNPDNO. Donde el nombre no haga match en el catálogo se conservará más
    # abajo el texto normalizado, para no perder capacidad de diferenciación
    crear_llave_matching("entidad_nacimiento") |>
    left_join(
        cat_ent_ext |> crear_llave_matching("entidad") |> select(LLAVE_ENT, cve_ent_nac = cve_ent),
        by = "LLAVE_ENT"
    ) |>
    select(-LLAVE_ENT) |>
    relocate(cve_ent_nac, .before = entidad_nacimiento) |>

    mutate(

        # ID PERSONA: mismos componentes y misma limpieza que en RNPDNO (ver
        # arriba), para que el hash sea comparable entre ambas bases. Como
        # componente de entidad de nacimiento se usa la clave INEGI; si no
        # hubo match en el catálogo, el nombre normalizado
        id_persona = paste0(
            coalesce(limpiar_curp(curp), ""),
            coalesce(limpiar_texto_id(nombres), ""),
            coalesce(limpiar_apellido(primer_apellido), ""),
            coalesce(limpiar_apellido(segundo_apellido), ""),
            coalesce(limpiar_sexo(sexo), ""),
            coalesce(as.character(fha_nac |> as.Date()), ""),
            coalesce(cve_ent_nac, limpiar_texto_id(entidad_nacimiento), "")
        ) |> openssl::sha1() |> as.character(),

        # Sin CURP y sin nombre suficiente (nombre + primer apellido) no hay
        # forma de identificar a la persona: el id_persona se anula para no
        # colapsar registros de personas distintas en un mismo identificador
        id_persona = if_else(
            is.na(limpiar_curp(curp)) &
                (is.na(limpiar_texto_id(nombres)) | is.na(limpiar_apellido(primer_apellido))),
            NA_character_,
            id_persona
        ),

        # Prelimpieza de ntra_ci e id_ci (sobreescribe las columnas originales;
        # na_if("") para que lo que quede vacío tras la limpieza cuente como NA)
        # TODO: Refinamiento de la limpieza y extensión de diccionario
        ntra_ci = ntra_ci |> str_remove_all("\\s") |> str_to_upper() |> stri_trans_general("Latin-ASCII") |> str_remove_all("SINDATOS") |> na_if(""),
        id_ci   = id_ci   |> str_remove_all("\\s") |> str_to_upper() |> stri_trans_general("Latin-ASCII") |> str_remove_all("SINDATOS") |> na_if(""),

        # Número de carpeta utilizable: ntra_ci si tras filtrar caracteres le
        # quedan más de 2 (menos no alcanzan a identificar una carpeta); en
        # caso contrario (corto, vacío o NA) se rescata id_ci
        carpeta_ci = ntra_ci |> str_replace_all("[^0-9A-Z/-]", "") |> na_if(""),
        carpeta_ci = if_else(str_length(coalesce(carpeta_ci, "")) <= 2L, id_ci, carpeta_ci),

        # ID CARPETA: entidad federativa + "/" + número de carpeta. Blindado
        # contra componentes vacíos: sin entidad o sin número de carpeta
        # utilizable, el id_carpeta completo queda en NA — nunca ids "a
        # medias" tipo "entidad/" o "/123", que colapsarían carpetas distintas
        id_carpeta = if_else(
            is.na(entidad_reporta) | is.na(carpeta_ci),
            NA_character_,
            paste0(
                entidad_reporta |> str_squish() |> str_to_upper() |> str_replace_all("\\s", "_") |> stri_trans_general("Latin-ASCII"),
                "/",
                carpeta_ci
            )
        ),

        # ID REGISTRO: hash SHA-1 de id_persona (cuando existe) + llave
        # (validada arriba: nunca es NA) + lugar donde fue vista la persona +
        # un conjunto de columnas que, en conjunto, han probado diferenciar
        # registros incluso cuando no se cuenta con nombre ni CURP (id_vicf,
        # sexo, pob, disc, fecha de nacimiento, edad, nacionalidad y folio
        # RNPDNO). Así todo registro obtiene un id_registro no vacío
        id_registro = str_c(
    coalesce(id_persona, ""),
    llave,
    coalesce(as.character(no_banci), ""),
    coalesce(municipio_visto, ""),
    coalesce(lugar_ultimo_contacto, ""),
    coalesce(as.character(id_vicf), ""),
    coalesce(limpiar_sexo(sexo), ""),
    coalesce(as.character(pob), ""),
    coalesce(as.character(disc), ""),
    coalesce(as.character(fha_nac |> as.Date()), ""),
    coalesce(as.character(edad), ""),
    coalesce(as.character(nacional), ""),
    coalesce(as.character(folio_rnpdno), ""),
    sep = "_"
) |> openssl::sha1() |> as.character()
    ) |>

    # Tirar columna temporal del número de carpeta
    select(-carpeta_ci) |>

    # Verificar duplicados de id_registro y eliminar solo los duplicados exactos
    verificar_deduplicar_id_registro(nombre_base = "BANCI") |>

    # Reportar registros sin id_carpeta (revisar) y sin id_persona (por diseño)
    reportar_cobertura_ids(nombre_base = "BANCI")

    # Contar: en el registro i, se cuentan las carpetas asociadas a la persona p_i
    # y la cantidad de personas asociadas a la carpeta c_i. Se hacen dos agrupamientos
    # para contabilizar esto.

# Entidades que no cruzaron con el catálogo: el pipeline las conserva vía
# fallback (nombre en title case / texto normalizado), pero generan prefijos
# de id_carpeta no homologados y componentes de id_persona basados en texto
# libre en lugar de la clave INEGI, así que conviene revisarlas
entidades_sin_cruce <- banci |>
    filter(is.na(cve_ent) & !is.na(entidad_reporta)) |>
    distinct(entidad_reporta) |>
    pull(entidad_reporta)

if (length(entidades_sin_cruce) > 0) {
    warning("¡Atención! Entidades federativas en BANCI sin cruce con el catálogo: ",
            paste(entidades_sin_cruce, collapse = ", "))
}

entidades_nac_sin_cruce <- banci |>
    filter(is.na(cve_ent_nac) & !is.na(entidad_nacimiento)) |>
    distinct(entidad_nacimiento) |>
    pull(entidad_nacimiento)

if (length(entidades_nac_sin_cruce) > 0) {
    warning("¡Atención! Entidades de nacimiento en BANCI sin cruce con el catálogo: ",
            paste(entidades_nac_sin_cruce, collapse = ", "))
}

# —————————————————————————————————————————————————————————————————————————————


# GAURDAR BASES (TEMPORAL)
# —————————————————————————————————————————————————————————————————————————————
write_xlsx_atdt(rnpdno, "output/rnpdno_con_ids.xlsx", parse_names = FALSE)
write_xlsx_atdt(banci, "output/banci_con_ids.xlsx", parse_names = FALSE)
# —————————————————————————————————————————————————————————————————————————————

# # EXPLORATORIO
# # —————————————————————————————————————————————————————————————————————————————

# rnpdno |> count(id_carpeta) |> filter(n != 1) |> arrange(desc(n))
# rnpdno |> filter(id_carpeta == "8b9951bb/5") |> write_xlsx_atdt("temp/temp.xlsx")

# # rnpdno_raw |> mutate(expediente = expediente |> str_remove_all("\\s")) |> filter(str_detect(expediente, "^.{1,3}$|[A-Za-zÑÁÉÍÓÚññaéíóú]{5,}"))

# banci |> colnames()
# rnpdno |> colnames()

# # VER LOS HEADS (stri_write_lines: UTF-8 garantizado y sobreescribe sin bloquear el archivo)
# # banci |> head(2) |> format(width = Inf) |> stri_write_lines("temp/temp.txt")
# # rnpdno |> head(2) |> format(width = Inf) |> stri_write_lines("temp/temp.txt")

# banci |> glimpse(50)
# rnpdno |> glimpse(38)

# rnpdno |> count(id_persona, sort = TRUE)
# banci |> count(id_persona, sort = TRUE)
# rnpdno |> count(id_carpeta, sort = TRUE)
# banci |> count(id_carpeta, sort = TRUE)
# banci |> filter(id_persona == "04ea764698493a83fed137c1207ba18701539179")
# # write_xlsx_atdt("temp/persona_mas_repetida.xlsx")

# # —————————————————————————————————————————————————————————————————————————————

# Contar id_perssona_sha1 únicos
num_id_persona_sha1_unicos <- banci |> 
  filter(!is.na(id_persona)) |> 
  distinct(id_persona) |>
  nrow()

# Contar id_carpeta_sha1 únicos
num_id_carpeta_sha1_unicos <- banci |> 
  filter(!is.na(id_carpeta)) |> 
  distinct(id_carpeta) |>
  nrow()

# Contar id_registro_sha1 únicos
num_id_registro_sha1_unicos <- banci |> 
  filter(!is.na(id_registro)) |> 
  distinct(id_registro) |>
  nrow()


# Acomodar columnas y renombrar para exportar a Excel
banci <-banci |> 
  select(
    entidad_reporta_desaparicion = entidad_reporta,
    municipio_desaparicion = nom_mun_hchos,
    carpeta_investigacion_banci = ntra_ci,
    id_carpeta_investigacion_banci = id_carpeta,

    fecha_de_hechos_banci = fha_de_hchos,

    # Datos de la persona desaparecida
    sexo,
    fecha_nacimiento_banci = fha_nac,
    localizado_o_no_localizado_banci = localizado_o_no_localizado,
    nombres_banci = nombres,
    primer_apellido_banci = primer_apellido,
    segundo_apellido_banci = segundo_apellido,
    localizado_o_no_localizado_banci = localizado_o_no_localizado,
    curp_limpia_banci = curp_limpia,

    # Datos de IDs
    id_persona,
    id_carpeta,
    id_registro
  )

# Guardar
banci |> 
  openxlsx::write.xlsx(here::here("RNPDNO",
             "output",
             "cruces_banci_rnpdno",
             "cruces_banci_rnpdno_28072026",
             "Base_BANCI_sin_match_con_RNPDNO_sexenio.xlsx"))
