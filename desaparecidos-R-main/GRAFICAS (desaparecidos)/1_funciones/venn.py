from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import font_manager
import squarify 
import pandas as pd
import random

from funciones import limpiar_svg_con_scour 
from funciones import get_text_color_for_bg 
from funciones import mostrar_guardar_figura

import textwrap
def wrap_text(text, ax, fig, max_width, fontsize, fontweight):
    if ' ' not in text:
        return text
    for width in range(len(text), 1, -1):
        candidate = '\n'.join(textwrap.wrap(text, width=width, break_long_words=False))
        t = ax.text(0, 0, candidate, fontsize=fontsize, fontweight=fontweight)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bbox = t.get_window_extent(renderer=renderer)
        inv = ax.transData.inverted()
        bbox_data = inv.transform(bbox)
        text_width = bbox_data[1][0] - bbox_data[0][0]
        t.remove()
        if text_width <= max_width:
            return candidate
    # Fuerza una palabra por línea si nada cabe
    candidate = '\n'.join(textwrap.wrap(text, width=1, break_long_words=False))
    return candidate


# Función para ajustar el tamaño de fuente para que el texto no se salga del rectángulo
def ajustar_fontsize(ax, fig, texto, max_width, base_size, fontweight):
    fontsize = base_size
    t = ax.text(0, 0, texto, fontsize=fontsize, fontweight=fontweight)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bbox = t.get_window_extent(renderer=renderer)
    inv = ax.transData.inverted()
    bbox_data = inv.transform(bbox)
    text_width = bbox_data[1][0] - bbox_data[0][0]
    t.remove()
    while text_width > max_width and fontsize > 6:
        fontsize -= 1
        t = ax.text(0, 0, texto, fontsize=fontsize, fontweight=fontweight)
        fig.canvas.draw()
        bbox = t.get_window_extent(renderer=renderer)
        bbox_data = inv.transform(bbox)
        text_width = bbox_data[1][0] - bbox_data[0][0]
        t.remove()
    return fontsize


    

def venn(
        df,                             # DataFrame de entrada (primera columna: etiquetas, segunda columna: valores numéricos)
        nombre=None,                    # Nombre base para archivos de salida (str o None)
        area_min=0.001,                 # Área mínima para mostrar texto en el rectángulo (float, típicamente entre 0 y 0.01)
        tipo_letra='Montserrat',        # Tipo de letra para todo el texto en la gráfica (str, ejemplo: 'Montserrat', 'Arial')
        tam_letra_etiqueta=26,          # Tamaño de letra para las etiquetas (int)
        tam_letra_valor=26,             # Tamaño de letra para los valores numéricos (int)
        tam_letra_porcentaje=26,        # Tamaño de letra para los porcentajes (int)
        paleta_colores=None,            # Lista de colores para los rectángulos (list de str HEX, ejemplo: ['#10302C', ...] o None para usar la paleta por defecto)
        porce_parentesis=False,         # Mostrar porcentaje entre paréntesis junto al valor (bool: True/False)
        ancho_fig=16,                   # Ancho de la figura en pulgadas (int o float)
        alto_fig=10,                    # Alto de la figura en pulgadas (int o float)
        color_borde_rec="white",        # Color del borde de los rectángulos (str HEX, ejemplo: 'white', '#000000')
        ancho_borde_rec=1,              # Grosor del borde de los rectángulos (int o float)
        mostrar_fig=True,               # Mostrar la figura al terminar (bool: True/False)
        guardar_fig=True,               # Guardar la figura al terminar (bool: True/False)
        ):

    # Configuración de fuentes y colores
    font_config = {
        'family': tipo_letra,
        'etiquetas': {'size': tam_letra_etiqueta, 'weight': 'bold', 'color': '#ffffff'},
        'valor': {'size': tam_letra_valor, 'weight': 'bold', 'color': '#ffffff'},
        'porcentaje': {'size': tam_letra_porcentaje, 'weight': 'medium', 'color': '#ffffff'}
    }

   # Configuración para que el texto en SVG sea editable.
    plt.rcParams['svg.fonttype'] = 'none'
    # Carga de fuentes personalizadas desde la carpeta de fuentes.
    font_dirs = [Path("../0_fonts")]
    font_files = font_manager.findSystemFonts(fontpaths=font_dirs)
    for font_file in font_files:
        font_manager.fontManager.addfont(font_file)
    plt.rc('font', family=tipo_letra)  # Aplica la fuente a toda la gráfica

    # Asegurar que todos los valores sean numéricos tipo float
    df.iloc[:, 1] = pd.to_numeric(
        df.iloc[:, 1], errors='coerce'
    ).fillna(0).astype(float)

    # Ordenar y calcular porcentaje
    df = df.sort_values(by=df.columns[1], ascending=False).copy()
    total_nacional = df.iloc[:, 1].sum()
    df['Porcentaje'] = (df.iloc[:, 1] / total_nacional * 100).round(1)

    # --- Colores por paleta_colores ---
    n = len(df)
    if paleta_colores is None:
        paleta_colores = ['#10302C', '#4C6A67', '#9B2247', '#9D792A', '#D5B162', '#767676']
    colores = list(paleta_colores[:n])  # Usa solo los colores dados, sin repetir
    if len(colores) < n:
        # Si faltan colores, agrega aleatorios
        for _ in range(n - len(colores)):
            color_rand = "#{:06x}".format(random.randint(0, 0xFFFFFF))
            colores.append(color_rand)

    # Configurar la figura
    plt.rc('font', family=font_config['family'])
    fig, ax = plt.subplots(figsize=(ancho_fig, alto_fig), dpi=300)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.axis('off')  # <-- Oculta los ejes y los números







    # # Dibuja el borde externo del treemap
    ax.add_patch(
        plt.Rectangle(
            (0, 0), 1, 1,
            fill=False,
            edgecolor=color_borde_rec,
            linewidth=ancho_borde_rec,
            zorder=20,
            clip_on=False  
        )
    )
    plt.tight_layout()

    mostrar_guardar_figura(
        fig=fig,
        ax=ax,
        nombre_df=nombre or "treemap",
        guardar_fig=guardar_fig,         # <-- Usa el argumento aquí
        mostrar_fig=mostrar_fig,         # <-- Usa el argumento aquí
        limpiar_svg_con_scour=limpiar_svg_con_scour
    )