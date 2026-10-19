
#
# Fecha:          20/07/2026
#
# Última
# actualización:  23/07/2026
#
# —————————————————————————————————————————————————————————————————————————————
# PREAMBULO --------
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
# FUNCIONES --------
# —————————————————————————————————————————————————————————————————————————————

# Source de carpeta utils/funciones_cat_geo_inegi.R para cargar diversas funciones
# Buscar la cola "*banci_rnpdno_ids_portal_matching/utils/funciones_cat_geo_inegi.R" en el proyecto
funciones_cat_geo_inegi_path <- dir_ls(here::here(), recurse = TRUE, glob = "*banci_rnpdno_ids_portal_matching/utils/funciones_cat_geo_inegi.R")
source(funciones_cat_geo_inegi_path)

# Llamar de forma implícita a la carpeta 
# glob con "*" busca toda dirección con cola anterior a "utils/funciones_cat_geo_inegi.R"
# archivo <- dir_ls(here::here(), recurse = TRUE, glob = "*utils/funciones_cat_geo_inegi.R")
# source(archivo)

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

        # Columna inconsistente
        columnas_inconsistentes_revision <- df |>
            group_by(id_registro) |>
            filter(n() > 1) |>
            summarise(across(all_of(columnas_inconsistentes), ~ n_distinct(.x) > 1),
                      .groups = "drop") |>
            filter(if_any(all_of(columnas_inconsistentes))) |> 
            select(-id_registro) |> names()

        # Si la inconsistencia en en el nombre o nombre_completo_victima esto significa que no se pudo formar un id_persona (porque no hay nombre con apellido materno o paterno ni CURP) entonces hacemos un distinct de id_registro

        columnas_nombre <- c("nombres", "nombre_completo_victima")

        if (length(columnas_inconsistentes_revision) > 0 &&
    any(columnas_nombre %in% columnas_inconsistentes_revision) &&
    all(columnas_inconsistentes_revision %in% columnas_nombre)) {
            message(">> ", nombre_base, ": la inconsistencia en 'nombres' o 'nombre_completo_victima' indica que no se pudo formar un id_persona (falta nombre con apellido materno o paterno o CURP). Se hará un distinct de id_registro.")

            df <- df |> distinct(id_registro, .keep_all = TRUE)
        } else {
            
            stop("En ", nombre_base, " hay ", ids_inconsistentes, " id_registro ",
            "duplicados con valores diferentes en: ",
            paste(columnas_inconsistentes_revision, collapse = ", "),
            ". El id_registro no está diferenciando bien los registros; ",
           "revisar los datos o el diseño del identificador antes de continuar.")
        }
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
# DATA ------------
# —————————————————————————————————————————————————————————————————————————————

#' Cargar catálogo de entidades federativas de INEGI
#'
#' Obtiene el catálogo de entidades federativas desde la fuente indicada
#' explícitamente: si `usar_get_geo_inegi = TRUE`, lo consulta en el servidor
#' con `get_geo_inegi()`; si es `FALSE`, usa el objeto
#' `catalogo_estados_inegi` del environment global. Si la fuente elegida no
#' está disponible, detiene la ejecución con un error (no hay fallback
#' silencioso a la otra fuente).
#'
#' @param extendido Lógico. Si es `TRUE` (por defecto), devuelve el catálogo
#'   con claves de 2 dígitos e incluye la clave `"33"` = `"Extranjero"`.
#'   Si es `FALSE`, devuelve el catálogo tal como viene de la fuente.
#' @param usar_get_geo_inegi Lógico. Si es `TRUE` (por defecto), consulta el
#'   catálogo con `get_geo_inegi()`. Si es `FALSE`, usa
#'   `catalogo_estados_inegi` del environment global.
#'
#' @return Un tibble con las columnas `cve_ent` (clave de entidad) y
#'   `entidad` (nombre de la entidad).
#'
#' @examples
#' \dontrun{
#' cat_ent_ext <- cargar_cat_ent()
#' cat_ent     <- cargar_cat_ent(extendido = FALSE)
#' cat_ent_loc <- cargar_cat_ent(usar_get_geo_inegi = FALSE)
#' }
#'
#' @export
cargar_cat_ent <- function(extendido = TRUE, usar_get_geo_inegi = FALSE) {

  if (!isTRUE(usar_get_geo_inegi) && !isFALSE(usar_get_geo_inegi)) {
    stop("'usar_get_geo_inegi' debe ser TRUE o FALSE.", call. = FALSE)
  }

  # Insumo 0: catálogo de entidades
  if (usar_get_geo_inegi) {
    # Consulta en el servidor
    if (!exists("get_geo_inegi", mode = "function")) {
      stop("Se pidió usar get_geo_inegi(), pero la función no existe. ",
           "Cargarla antes o usar usar_get_geo_inegi = FALSE.", call. = FALSE)
    }
    cat_ent <- get_geo_inegi("entidades") |>
      select(CVE_ENT, entidad = NOM_ENT) |>
      clean_names()

  } else {
    # Catálogo que ya debe estar en el environment global
    if (!exists("catalogo_estados_inegi", envir = globalenv())) {
      stop("Se pidió usar catalogo_estados_inegi, pero no existe en el ",
           "environment global. Cargarlo antes o usar usar_get_geo_inegi = TRUE.",
           call. = FALSE)
    }
    cat_ent <- get("catalogo_estados_inegi", envir = globalenv()) |>
      select(cve_ent, entidad = nom_ent)
  }

  if (!extendido) return(cat_ent)

  # Catálogo extendido: claves de 2 dígitos e incluir 33 = Extranjero
  cat_ent |>
    mutate(cve_ent = cve_ent |> as.character() |>
                    stringr::str_pad(side = "left", pad = "0", width = 2)) |>
    filter(cve_ent != "33") |>
    add_row(cve_ent = "33", entidad = "Extranjero")
}

# —————————————————————————————————————————————————————————————————————————————
# CONSTRUCCIÓN DE IDENTIFICADORES (RNPDNO + BANCI) -------- 
# —————————————————————————————————————————————————————————————————————————————
# Pegar DEBAJO de la sección FUNCIONES. Usa como herramientas:
#   limpiar_texto_id(), limpiar_apellido(), limpiar_curp(), limpiar_sexo(),
#   placeholders_apellido, verificar_deduplicar_id_registro(),
#   reportar_cobertura_ids(), cargar_cat_ent()
# y además crear_llave_matching() (utils).
# Paquetes: dplyr, stringr, stringi, openssl.

# Columnas requeridas para construir los identificadores de cada base
columnas_requeridas_rnpdno <- c(
    # Identificación de la persona
    "curp_victima", "nombre_vic", "primerapellido_vic", "segundoapellido_vic",
    "sexo", "fechanacimiento", "idestadonacimiento_vic",
    # Entidad de desaparición
    "estado_desaparicion", "cve_estado_desaparicion",
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
    "llave", "no_banci", "municipio_visto", "lugar_ultimo_contacto", "id_vicf",
    "pob", "disc", "edad", "nacional", "folio_rnpdno"
)

#' Validar insumos de identificadores
#' @descripcion Verifica que existan las columnas requeridas en ambas bases y
#' que los insumos mínimos del id_registro (fub en RNPDNO, llave en BANCI)
#' nunca estén vacíos. Reporta (warning) cuántos registros traen placeholders
#' en los apellidos. Falla temprano y con mensajes claros.
#' @param rnpdno Data frame RNPDNO.
#' @param banci Data frame BANCI.
#' @return TRUE invisible si todo está en orden.
validar_insumos_ids <- function(rnpdno, banci) {

    faltan_rnpdno <- setdiff(columnas_requeridas_rnpdno, names(rnpdno))
    if (length(faltan_rnpdno) > 0) {
        stop("¡Faltan columnas requeridas en RNPDNO: ",
             paste(faltan_rnpdno, collapse = ", "), call. = FALSE)
    }

    faltan_banci <- setdiff(columnas_requeridas_banci, names(banci))
    if (length(faltan_banci) > 0) {
        stop("¡Faltan columnas requeridas en BANCI: ",
             paste(faltan_banci, collapse = ", "), call. = FALSE)
    }

    # fub y llave son el insumo mínimo del id_registro de cada base
    if (any(is.na(rnpdno$fub))) {
        stop("¡Atención! Hay registros con fub vacío en RNPDNO. No se puede continuar ",
             "dado que el fub es el insumo del id_registro. Revisar los datos.",
             call. = FALSE)
    }
    if (any(is.na(banci$llave))) {
        stop("¡Atención! Hay registros con llave vacía en BANCI. No se puede continuar ",
             "dado que la llave es el insumo del id_registro. Revisar los datos.",
             call. = FALSE)
    }

    # Placeholders en apellidos: solo se reportan para dimensionar el problema
    # (al construir el id_persona se tratan como NA vía limpiar_apellido())
    avisar_placeholders <- function(ap1, ap2, nombre_base) {
        n <- sum(limpiar_texto_id(ap1) %in% placeholders_apellido |
                     limpiar_texto_id(ap2) %in% placeholders_apellido)
        if (n > 0) {
            warning("¡Atención! Hay ", n, " registros en ", nombre_base, " con un ",
                    "placeholder (", paste(str_to_upper(placeholders_apellido), collapse = ", "),
                    ") en alguno de los apellidos. Se tratarán como NA en los identificadores.",
                    call. = FALSE)
        }
    }
    avisar_placeholders(rnpdno$primerapellido_vic, rnpdno$segundoapellido_vic, "RNPDNO")
    avisar_placeholders(banci$primer_apellido, banci$segundo_apellido, "BANCI")

    invisible(TRUE)
}

#' Construir identificadores en RNPDNO
#' @descripcion Agrega nombres de entidades y construye id_persona,
#' id_carpeta e id_registro; después deduplica y reporta cobertura.
#' @param df Data frame RNPDNO (comprimido).
#' @param cat_ent_ext Catálogo extendido de entidades (cargar_cat_ent()).
#' @return Data frame con identificadores.
procesar_ids_rnpdno <- function(df, cat_ent_ext) {

    df |>

        # Agregar nombres de entidades con cat_ent_ext (claves numéricas, 33 = Extranjero)
        mutate(
            cve_ent_nac = idestadonacimiento_vic |> str_pad(side = "left", pad = "0", width = 2)
        ) |>
        # Unir nombres: entidad de nacimiento de la víctima
        left_join(cat_ent_ext |> rename(estadonacimiento_vic = entidad),
                  by = c("cve_ent_nac" = "cve_ent")) |>
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
            # normalizados. Mismos componentes y limpieza que en BANCI
            id_persona = paste0(
                coalesce(limpiar_curp(curp_victima), ""),
                coalesce(limpiar_texto_id(nombre_vic), ""),
                coalesce(limpiar_apellido(primerapellido_vic), ""),
                coalesce(limpiar_apellido(segundoapellido_vic), ""),
                coalesce(limpiar_sexo(sexo), ""),
                coalesce(as.character(fechanacimiento |> as.Date()), ""),
                coalesce(idestadonacimiento_vic |> str_pad(side = "left", pad = "0", width = 2), "")
            ) |> openssl::sha1() |> as.character(),

            # Sin CURP y sin nombre suficiente (nombre + primer apellido) el
            # id_persona se anula para no colapsar personas distintas
            id_persona = if_else(
                is.na(limpiar_curp(curp_victima)) &
                    (is.na(limpiar_texto_id(nombre_vic)) | is.na(limpiar_apellido(primerapellido_vic))),
                NA_character_,
                id_persona
            ),

            # ID CARPETA: normalizar el expediente y quitar los patrones basura
            id_carpeta = expediente |>
                stri_trans_general("Latin-ASCII") |>
                str_to_upper() |>
                str_squish() |>
                str_remove_all(regex(
                    str_c("(?:", c("^S/D$", "SECUESTROS"), ")", collapse = "|"),
                    ignore_case = TRUE
                )) |>
                str_squish(),

            # Expedientes de 3 caracteres o menos no identifican una carpeta
            id_carpeta = if_else(str_length(id_carpeta) < 4L, NA_character_, id_carpeta),

            # Anteponer la dependencia de origen (hash corto de 8 caracteres,
            # mismo que en cat_fiscalias); sin expediente válido queda en NA
            id_carpeta = if_else(
                is.na(id_carpeta),
                NA_character_,
                paste0(
                    coalesce(dependencia_origen |> str_squish() |> str_to_lower() |>
                                 stri_trans_general("Latin-ASCII") |> openssl::sha1() |>
                                 str_sub(1L, 8L), ""),
                    "/",
                    id_carpeta
                )
            ),

            # ID REGISTRO: hash SHA-1 del fub sin espacios (nunca es NA)
            # Actualización
            id_registro = fub # |> str_remove_all("\\s") |> openssl::sha1() |> as.character()
        ) |>

        verificar_deduplicar_id_registro(nombre_base = "RNPDNO") |>
        reportar_cobertura_ids(nombre_base = "RNPDNO")
}

#' Construir identificadores en BANCI
#' @descripcion Homologa entidades contra el catálogo INEGI y construye
#' id_persona, id_carpeta e id_registro; después deduplica y reporta cobertura.
#' @param df Data frame BANCI (subeR).
#' @param cat_ent Catálogo de entidades (cargar_cat_ent(extendido = FALSE)).
#' @param cat_ent_ext Catálogo extendido de entidades (cargar_cat_ent()).
#' @return Data frame con identificadores.
procesar_ids_banci <- function(df, cat_ent, cat_ent_ext) {

    df |>

        # ENTIDAD FEDERATIVA (del registro): homologar contra el catálogo INEGI
        crear_llave_matching("entidad_reporta") |>
        left_join(cat_ent |> crear_llave_matching("entidad"), by = "LLAVE_ENT") |>
        # TODO: pasar un str_to_title() con cautela
        mutate(entidad_reporta = coalesce(entidad, str_to_title(entidad_reporta))) |>
        select(-LLAVE_ENT, -entidad) |>
        relocate(cve_ent, .before = entidad_reporta) |>

        # ENTIDAD DE NACIMIENTO: clave INEGI de 2 dígitos (33 = Extranjero)
        crear_llave_matching("entidad_nacimiento") |>
        left_join(
            cat_ent_ext |> crear_llave_matching("entidad") |> select(LLAVE_ENT, cve_ent_nac = cve_ent),
            by = "LLAVE_ENT"
        ) |>
        select(-LLAVE_ENT) |>
        relocate(cve_ent_nac, .before = entidad_nacimiento) |>

        mutate(

            # ID PERSONA: mismos componentes y limpieza que en RNPDNO. Entidad de
            # nacimiento: clave INEGI o, si no hubo match, el nombre normalizado
            id_persona = paste0(
                coalesce(limpiar_curp(curp), ""),
                coalesce(limpiar_texto_id(nombres), ""),
                coalesce(limpiar_apellido(primer_apellido), ""),
                coalesce(limpiar_apellido(segundo_apellido), ""),
                coalesce(limpiar_sexo(sexo), ""),
                coalesce(as.character(fha_nac |> as.Date()), ""),
                coalesce(cve_ent_nac, limpiar_texto_id(entidad_nacimiento), "")
            ) |> openssl::sha1() |> as.character(),

            id_persona = if_else(
                is.na(limpiar_curp(curp)) &
                    (is.na(limpiar_texto_id(nombres)) | is.na(limpiar_apellido(primer_apellido))),
                NA_character_,
                id_persona
            ),

            # Prelimpieza de ntra_ci e id_ci
            # TODO: Refinamiento de la limpieza y extensión de diccionario
            ntra_ci = ntra_ci |> str_remove_all("\\s") |> str_to_upper() |>
                stri_trans_general("Latin-ASCII") |> str_remove_all("SINDATOS") |> na_if(""),
            id_ci   = id_ci |> str_remove_all("\\s") |> str_to_upper() |>
                stri_trans_general("Latin-ASCII") |> str_remove_all("SINDATOS") |> na_if(""),

            # Número de carpeta: ntra_ci si le quedan más de 2 caracteres; si no, id_ci
            carpeta_ci = ntra_ci |> str_replace_all("[^0-9A-Z/-]", "") |> na_if(""),
            carpeta_ci = if_else(str_length(coalesce(carpeta_ci, "")) <= 2L, id_ci, carpeta_ci),

            # ID CARPETA: entidad + "/" + número de carpeta; NA si falta algo
            id_carpeta = if_else(
                is.na(entidad_reporta) | is.na(carpeta_ci),
                NA_character_,
                paste0(
                    entidad_reporta |> str_squish() |> str_to_upper() |>
                        str_replace_all("\\s", "_") |> stri_trans_general("Latin-ASCII"),
                    "/",
                    carpeta_ci
                )
            ),

            # ID REGISTRO: hash SHA-1 de id_persona + llave + columnas que
            # diferencian registros aun sin nombre ni CURP
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

        select(-carpeta_ci) |>
        verificar_deduplicar_id_registro(nombre_base = "BANCI") |>
        reportar_cobertura_ids(nombre_base = "BANCI")
}

#' Revisar entidades de BANCI sin cruce con el catálogo
#' @descripcion Avisa (warning) qué entidades federativas y de nacimiento no
#' hicieron match con el catálogo INEGI: el pipeline las conserva vía
#' fallback, pero generan prefijos de id_carpeta no homologados y componentes
#' de id_persona basados en texto libre. Regresa el data frame sin cambios.
#' @param banci Data frame BANCI ya procesado.
#' @return El mismo data frame (invisible).
revisar_entidades_sin_cruce <- function(banci) {

    entidades_sin_cruce <- banci |>
        filter(is.na(cve_ent) & !is.na(entidad_reporta)) |>
        distinct(entidad_reporta) |>
        pull(entidad_reporta)

    if (length(entidades_sin_cruce) > 0) {
        warning("¡Atención! Entidades federativas en BANCI sin cruce con el catálogo: ",
                paste(entidades_sin_cruce, collapse = ", "), call. = FALSE)
    }

    entidades_nac_sin_cruce <- banci |>
        filter(is.na(cve_ent_nac) & !is.na(entidad_nacimiento)) |>
        distinct(entidad_nacimiento) |>
        pull(entidad_nacimiento)

    if (length(entidades_nac_sin_cruce) > 0) {
        warning("¡Atención! Entidades de nacimiento en BANCI sin cruce con el catálogo: ",
                paste(entidades_nac_sin_cruce, collapse = ", "), call. = FALSE)
    }

    invisible(banci)
}

#' Construir identificadores para RNPDNO y BANCI
#' @descripcion Función principal: valida insumos, construye id_persona,
#' id_carpeta e id_registro en ambas bases, deduplica, reporta cobertura y
#' revisa entidades sin cruce. Los catálogos se cargan con cargar_cat_ent()
#' si no se proporcionan, desde la fuente indicada en `usar_get_geo_inegi`.
#' @param comprimido Data frame RNPDNO.
#' @param subeR Data frame BANCI (subeR_limpia_no_localizados).
#' @param cat_ent Catálogo de entidades; si es NULL se carga.
#' @param cat_ent_ext Catálogo extendido de entidades; si es NULL se carga.
#' @param usar_get_geo_inegi Lógico. Fuente de los catálogos que se carguen:
#'   `TRUE` (por defecto) usa get_geo_inegi(); `FALSE` usa
#'   catalogo_estados_inegi del environment global. Se ignora si ambos
#'   catálogos se pasan como argumento.
#' @return Lista con dos data frames: `rnpdno` y `banci`.
#' @examples
#' \dontrun{
#' ids <- construir_ids(comprimido, subeR_limpia_no_localizados)
#' ids <- construir_ids(comprimido, subeR_limpia_no_localizados,
#'                      usar_get_geo_inegi = FALSE)
#' comprimido <- ids$rnpdno
#' subeR_limpia_no_localizados <- ids$banci
#' }
construir_ids <- function(comprimido, subeR, cat_ent = NULL, cat_ent_ext = NULL,
                          usar_get_geo_inegi = TRUE) {

    if (!exists("crear_llave_matching", mode = "function")) {
        stop("No existe crear_llave_matching(). Cargar las utils antes de construir los ids.",
             call. = FALSE)
    }

    # Catálogos (solo se cargan si no se pasaron como argumento), desde la
    # fuente indicada explícitamente
    if (is.null(cat_ent)) {
        cat_ent <- cargar_cat_ent(extendido = FALSE,
                                  usar_get_geo_inegi = usar_get_geo_inegi)
    }
    if (is.null(cat_ent_ext)) {
        cat_ent_ext <- cargar_cat_ent(extendido = TRUE,
                                      usar_get_geo_inegi = usar_get_geo_inegi)
    }

    # Validar antes de procesar para fallar temprano
    validar_insumos_ids(comprimido, subeR)

    rnpdno <- procesar_ids_rnpdno(comprimido, cat_ent_ext)

    banci <- procesar_ids_banci(subeR, cat_ent, cat_ent_ext)
    revisar_entidades_sin_cruce(banci)

    list(rnpdno = rnpdno, banci = banci)
}

# Desde catalogo_estados_inegi en el environment
# ids <- construir_ids(comprimido, subeR_limpia_no_localizados, usar_get_geo_inegi = FALSE)