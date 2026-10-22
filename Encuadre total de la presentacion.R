


# Doble encuadre de datos
#install.packages("arrow")
library(arrow)
library(readr)
library(tidyverse)
library(broom)
library(skimr)


origen <- read_parquet("/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/input/rnpdno/reporte_personas_completo_19102026.parquet")

Maria <- read_parquet("/Users/alberto/Downloads/Resultado_1_Procesamiento_ETL_RNPDNO.parquet")

local_mio <- read_parquet("/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/output/Resultado_1_Procesamiento_ETL_RNPDNO_autonomo.parquet")
e <- skim(Maria)
f <- skim(local_mio)
table(f==e)
table(f==e)

#-------------------------Para pate2

Maria <- read_parquet("/Users/alberto/Downloads/Resultado_2_Procesamiento_ETL_BANCI.parquet")

viejo <- read_parquet("/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/output/Resultado_2_Procesamiento_ETL_BANCI.parquet")

local_mio <- read_parquet("/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/output/Resultado_2_Procesamiento_ETL_BANCI_autonomo.parquet")
e <- skim(Maria)
f <- skim(local_mio)
g <- skim(viejo)
table(e==g)
table(f==g)



#-------------------------Para pate3

Maria <- read_parquet("/Users/alberto/Downloads/Resultado_3_Procesamiento_ETL_PUI.parquet")

viejo <- read_parquet("/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/output/Resultado_3_Procesamiento_ETL_PUI.parquet")

local_mio <- read_parquet("/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/output/Resultado_3_Procesamiento_ETL_PUI_autonomo.parquet")
e <- skim(Maria)

g <- skim(viejo)

f <- skim(local_mio)

table(e==g)
table(f==g)





#--------- Encuadre de base total-------

Base_maestra_fin <- read_parquet("/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/output/Resultados_4_Generacion_Indicadores/reg_rn_min-max.parquet")



#-----Diapositiva ------
resumen <- skim(Base_maestra_fin)
Total_registros <- length(Base_maestra_fin$fub_rnpdno)
Desaparecidas <- Base_maestra_fin %>% 
  filter(clasificacion_des_derivada_rnpdno %in%
           c("Desaparecidos","Pendientes"))
length(Desaparecidas$fub_rnpdno)

localizadas <- Base_maestra_fin %>% 
  filter(clasificacion_des_derivada_rnpdno %in%
           c("Localizados"))
length(localizadas$fub_rnpdno)





#---------Filtro de fecha
larga <- library(dplyr)
library(lubridate)

larga_data <- Desaparecidas %>%
  mutate(
    fecha_filtro = as.Date(fecha_hechos_modificada_derivada_rnpdno)
  ) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro < ymd("2006-01-01")
  ) 

                       
length(larga_data$fub_rnpdno)



corta_data <- Desaparecidas %>%
  mutate(
    fecha_filtro = as.Date(fecha_hechos_modificada_derivada_rnpdno)
  ) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro >= lubridate::ymd("2006-01-01")
  )


length(corta_data$fub_rnpdno)





#-----localizadas---

localizadas_vida <- localizadas %>% filter(is_cvid_derivada_rnpdno==TRUE)
length(localizadas_vida$fub_rnpdno)

localizadas_svida <- localizadas %>% filter(is_svid_derivada_rnpdno==TRUE)
length(localizadas_svida$fub_rnpdno)


SinDelito <- localizadas %>%
  filter(!replace_na(is_cdel_derivada_rnpdno, FALSE))

ConDelito <- localizadas %>%
  filter(replace_na(is_cdel_derivada_rnpdno, FALSE))

length(ConDelito$fub_rnpdno)




#--- Diapositiva 2---------------

corta_data <- Desaparecidas %>%
  mutate(
    fecha_filtro = as.Date(fecha_hechos_modificada_derivada_rnpdno)
  ) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro >= lubridate::ymd("2006-01-01")
  )


length(corta_data$fub_rnpdno)


resumen_actividad <- corta_data %>%
  filter(estatus_loc_derivada_rnpdno == "des") %>%
  mutate(
    con_actividad_pui = coalesce(is_cind_derivada_pui, FALSE),
    datos_insuficientes = coalesce(is_sisf_derivada_rnpdno_pui, FALSE),
    categoria = case_when(
      con_actividad_pui ~ "Con actividad (registro administrativo en PUI)",
      datos_insuficientes ~ "Datos insuficientes",
      TRUE ~ "Sin actividad PUI a la fecha (CURP válida)"
    )
  )


#-------------corte del 27 de marzo del 2026-------
corta_data_hasta_marzo <- Desaparecidas %>%
  mutate(
    fecha_filtro = as.Date(fecha_hechos_modificada_derivada_rnpdno)
  ) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro <= lubridate::ymd("2026-03-25")
  )


#-------Para datos insuficientes---------
table(resumen_actividad$categoria)
actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Datos insuficientes")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
library(readxl)

# Línea base congelada de marzo
corte_marzo <- read_excel(
  "/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/input/datos_marzo/reg_rn_25mar26_des_sisf.xlsx",
  col_types = "text"
) %>%
  transmute(fub = str_trim(fub)) %>%
  filter(!is.na(fub), fub != "") %>%  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, corte_marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(corte_marzo, actual_sisf, by = "fub")
length(bajas$fub)



#-----Con actividad------


actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Con actividad (registro administrativo en PUI)")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
library(readxl)

marzo <- read_excel(
  "/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/input/datos_marzo/reg_rn_25mar26_des_cisf_cind.xlsx",
  col_types = "text"
) %>%
  transmute(fub = str_trim(fub)) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(marzo, actual_sisf, by = "fub")
length(bajas$fub)







#-----Sin actividad-------


actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Sin actividad PUI a la fecha (CURP válida)")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
library(readxl)

marzo <- read_excel(
  "/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/input/datos_marzo/reg_rn_25mar26_des_cisf_sind.xlsx",
  col_types = "text"
) %>%
  transmute(fub = str_trim(fub)) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(marzo, actual_sisf, by = "fub")
length(bajas$fub)






#-------------corte del 1 de julio del 2026-------
corta_data_hasta_julio <- Desaparecidas %>%
  mutate(
    fecha_filtro = as.Date(fecha_hechos_modificada_derivada_rnpdno)
  ) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro <= lubridate::ymd("2026-07-01")
  )


#-------Para datos insuficientes---------
table(resumen_actividad$categoria)
actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Datos insuficientes")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
library(readxl)

# Línea base congelada de marzo
corte_marzo <- read_excel(
  "/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/input/datos_julio/reg_rn_01jul26_des_sisf.xlsx",
  col_types = "text"
) %>%
  transmute(fub = fub_rnpdno) %>%
  filter(!is.na(fub), fub != "") %>%  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, corte_marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(corte_marzo, actual_sisf, by = "fub")
length(bajas$fub)



#-----Con actividad------


actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Con actividad (registro administrativo en PUI)")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
library(readxl)

marzo <- read_excel(
  "/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/input/datos_julio/reg_rn_01jul26_des_cisf_cind.xlsx",
  col_types = "text"
) %>%
  transmute(fub = fub_rnpdno) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(marzo, actual_sisf, by = "fub")
length(bajas$fub)







#-----Sin actividad-------


actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Sin actividad PUI a la fecha (CURP válida)")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
library(readxl)

marzo <- read_excel(
  "/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main/input/datos_julio/reg_rn_01jul26_des_cisf_sind.xlsx",
  col_types = "text"
) %>%
  transmute(fub = fub_rnpdno) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(marzo, actual_sisf, by = "fub")
length(bajas$fub)


#-------------Victima con carpeta de investigacion valida octubre 24 hasta  la fecha-----


base_desde_octubre <- Base_maestra_fin %>%
  mutate(fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno)) %>%
  filter(
    is.na(fecha_periodo) | fecha_periodo >= as.Date("2024-10-01")
  ) 
length(base_desde_octubre$fub_rnpdno)



Desaparecidas <- base_desde_octubre %>% 
  filter(clasificacion_des_derivada_rnpdno %in%
           c("Desaparecidos","Pendientes"))
length(Desaparecidas$fub_rnpdno)

localizadas <- base_desde_octubre %>% 
  filter(clasificacion_des_derivada_rnpdno %in%
           c("Localizados"))
length(localizadas$fub_rnpdno)


#---------------Con carpeta de investigacion por desaparicion forzada o particulares


Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>% summarise(
  con_match_banci = sum(tiene_match),
  por_desaparicion_forzada = sum(tiene_match & forzada),
  por_delitos_de_particulares = sum(tiene_match & particulares),
  sin_match_con_folio_valido = sum(!tiene_match & folio_valido),
  sin_match_sin_folio_valido = sum(!tiene_match & !folio_valido),
  sin_match_sin_folio_valido_estruc_inva = sum(!tiene_match & !folio_valido&!campo_vacio),
  sin_match_sin_folio_valido_vacio = sum(!tiene_match & !folio_valido&campo_vacio),
)





localizadas_vida <- localizadas %>% filter(is_cvid_derivada_rnpdno==TRUE)
length(localizadas_vida$fub_rnpdno)

localizadas_svida <- localizadas %>% filter(is_svid_derivada_rnpdno==TRUE)
length(localizadas_svida$fub_rnpdno)







SinDelito <- localizadas %>%
  filter(!replace_na(is_cdel_derivada_rnpdno, FALSE))
length(SinDelito$fub_rnpdno)

ConDelito <- localizadas %>%
  filter(replace_na(is_cdel_derivada_rnpdno, FALSE))

length(ConDelito$fub_rnpdno)



#Lamina 7 - Antes y despues de agosto

otros_delitos <- Desaparecidas %>% mutate(
  fecha = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)) %>% 
  filter(!tiene_match & folio_valido) %>% 
  mutate(
    periodo = case_when(
      !is.na(fecha) &
        fecha >= as.Date("2024-10-01") &
        fecha < as.Date("2025-08-01") ~ "Oct 2024–jul 2025",
      !is.na(fecha) &
        fecha >= as.Date("2025-08-01") ~ "Desde ago 2025",
      TRUE ~ NA_character_
    )
  ) %>%
  filter(!is.na(periodo)) %>%
  count(periodo, name = "registros")





# Estructura invalida
invalida <-  Desaparecidas %>% mutate(
  fecha = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)) %>% 
  filter(!tiene_match & !folio_valido&!campo_vacio) %>% 
  mutate(
    periodo = case_when(
      !is.na(fecha) &
        fecha >= as.Date("2024-10-01") &
        fecha < as.Date("2025-08-01") ~ "Oct 2024–jul 2025",
      !is.na(fecha) &
        fecha >= as.Date("2025-08-01") ~ "Desde ago 2025",
      TRUE ~ NA_character_
    )
  ) %>%
  filter(!is.na(periodo)) %>%
  count(periodo, name = "registros")








#Campo vacio
campo_vacio <- Desaparecidas %>% mutate(
  fecha = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)) %>% 
  filter(!tiene_match & !folio_valido&campo_vacio) %>% 
  mutate(
    periodo = case_when(
      !is.na(fecha) &
        fecha >= as.Date("2024-10-01") &
        fecha < as.Date("2025-08-01") ~ "Oct 2024–jul 2025",
      !is.na(fecha) &
        fecha >= as.Date("2025-08-01") ~ "Desde ago 2025",
      TRUE ~ NA_character_
    )
  ) %>%
  filter(!is.na(periodo)) %>%
  count(periodo, name = "registros")




# ----Lamina 9  ----


con_carpeta_FIN_A <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>% filter(tiene_match==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()




# ----Lamina 9  ----


con_carpeta_FIN_A <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>% filter(tiene_match==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()




# ----Lamina 10  ----


con_carpeta_FIN_O <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>%   filter(!tiene_match==TRUE & folio_valido==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()







# ----Lamina 11  ----


con_carpeta_FIN_O_11 <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>%   filter(!tiene_match==TRUE & !folio_valido==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()




# ----Lamina 12  ----


con_carpeta_FIN_O_12 <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>%   filter(!tiene_match==TRUE & !folio_valido&!campo_vacio==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()




# ----Lamina 13  ----


con_carpeta_FIN_O_13 <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>%   filter(!tiene_match==TRUE & !folio_valido&campo_vacio==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()


# ----Lamina 14  ----
con_carpeta_FIN_O_14 <- Desaparecidas %>% 
  mutate( grupo = case_when(
  coalesce(is_sisf_derivada_rnpdno_pui, FALSE) ~
    "Datos insuficientes",
  coalesce(is_cind_derivada_pui, FALSE) ~
    "Con actividad PUI",
  TRUE ~
    "Sin actividad PUI (CURP válida)")) %>% 
  mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha,grupo) %>% count()








# ----Lamina 16  ----
con_carpeta_FIN_O_16 <- Desaparecidas %>% 
    mutate(
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE)) %>% filter(!tiene_match==TRUE & folio_valido==TRUE) %>%   
  mutate(Fecha=format(fecha_periodo, "%Y-%m"),
             institucion = case_when(
               fiscalia ~ "Fiscalía",
               comision ~ "Comisión",
               portal ~ "Portal",
               TRUE ~ "Sin clasificar"
             )) %>% 
  group_by( institucion,nombre_entidad_derivada_rnpdno) %>% count()







# ----Lamina 17  ----
con_carpeta_FIN_O_17 <- Desaparecidas %>% 
  mutate(
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE)) %>% 
  filter(!tiene_match==TRUE & !folio_valido&!campo_vacio==TRUE) %>%   
  mutate(Fecha=format(fecha_periodo, "%Y-%m"),
         institucion = case_when(
           fiscalia ~ "Fiscalía",
           comision ~ "Comisión",
           portal ~ "Portal",
           TRUE ~ "Sin clasificar"
         )) %>% 
  group_by( institucion,nombre_entidad_derivada_rnpdno) %>% count()













# ----Lamina 18  ----
con_carpeta_FIN_O_18 <- Desaparecidas %>% 
  mutate(
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE)) %>% 
  filter(!tiene_match==TRUE & folio_valido==TRUE&fecha_periodo>= as.Date("2026-08-01") ) %>%   
  mutate(Fecha=format(fecha_periodo, "%Y-%m"),
         institucion = case_when(
           fiscalia ~ "Fiscalía",
           comision ~ "Comisión",
           portal ~ "Portal",
           TRUE ~ "Sin clasificar"
         )) %>% 
  group_by( institucion,nombre_entidad_derivada_rnpdno) %>% count()







# ----Lamina 19  ----
con_carpeta_FIN_O_19 <- Desaparecidas %>% 
  mutate(
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE)) %>% 
  filter(!tiene_match==TRUE & !folio_valido&!campo_vacio==TRUE&fecha_periodo>= as.Date("2026-08-01")) %>%   
  mutate(Fecha=format(fecha_periodo, "%Y-%m"),
         institucion = case_when(
           fiscalia ~ "Fiscalía",
           comision ~ "Comisión",
           portal ~ "Portal",
           TRUE ~ "Sin clasificar"
         )) %>% 
  group_by( institucion,nombre_entidad_derivada_rnpdno) %>% count()




# ----Lamina 20  ---
# ----Lamina 21  ----
# ----Lamina 22  ----






