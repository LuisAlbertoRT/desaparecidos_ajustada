"""
Engine centralizado y escalable para la sustitución de variables (texto e imágenes)
en plantillas de Microsoft PowerPoint (.pptx).
"""

from pathlib import Path
from typing import Dict, Any, Union, Tuple
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
import os


class PPTReportBuilder:
    """
    Motor para cargar una plantilla PPTX, aplicar un diccionario unificado de
    reemplazos de texto y de imágenes en un solo pase en memoria, y guardar el resultado.
    
    Resuelve problemas comunes de `python-pptx`:
    - Fragmentación de runs (run-splitting) a nivel de párrafo.
    - Soporte recursivo para formas dentro de grupos (GroupShapes) y tablas.
    - Sustitución exacta de cuadros de texto marcadores por imágenes.
    """

    def __init__(self, template_path: Union[str, Path]):
        self.template_path = Path(template_path)
        if not self.template_path.exists():
            raise FileNotFoundError(f"La plantilla PPTX no existe: {self.template_path}")
        
        self.prs = Presentation(str(self.template_path))
        self.text_replacements: Dict[str, str] = {}
        self.image_replacements: Dict[str, str] = {}

    def format_value(self, key: str, value: Any) -> str:
        """
        Formatea el valor según la clave y tipo de dato.
        """
        if value is None:
            return ""

        key_lower = str(key).lower()

        # Si es un año o clave que no requiere separadores de miles
        if 'año' in key_lower or 'anio' in key_lower or 'year' in key_lower:
            try:
                valor_num = float(value)
                return str(int(valor_num))
            except (ValueError, TypeError):
                return str(value)

        # Si el valor ya es un string con formato (ej. "23.5%", "1,500"), dejar tal cual
        if isinstance(value, str):
            return value

        # Intento de formatear números
        try:
            valor_num = float(value)
            if valor_num.is_integer():
                return "{:,.0f}".format(valor_num)
            else:
                return str(value)
        except (ValueError, TypeError):
            return str(value)

    def add_text_variables(self, variables: Dict[str, Any]) -> "PPTReportBuilder":
        """
        Agrega o actualiza variables de texto en el motor.
        """
        for k, v in variables.items():
            str_key = str(k).strip()
            self.text_replacements[str_key] = self.format_value(str_key, v)
        return self

    def add_image_variables(self, images: Dict[str, Union[str, Path]]) -> "PPTReportBuilder":
        """
        Agrega o actualiza mapeos de marcadores de imagen a rutas de archivos PNG/JPG.
        """
        for k, v in images.items():
            str_key = str(k).strip()
            self.image_replacements[str_key] = str(v)
        return self

    def _replace_in_paragraph(self, paragraph) -> Dict[str, int]:
        """
        Reemplaza variables en un párrafo.
        Resuelve el problema de 'run-splitting' concatenando cuando sea necesario.
        """
        counts = {k: 0 for k in self.text_replacements.keys()}
        full_p_text = paragraph.text

        if not full_p_text:
            return counts

        # Verificar si alguna clave existe en el texto del párrafo
        keys_present = []
        for key in self.text_replacements.keys():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in full_p_text:
                keys_present.append(key)

        if not keys_present:
            return counts

        # Estrategia 1: Intentar reemplazar dentro de runs individuales si el placeholder no está fragmentado
        for key in keys_present:
            placeholder = f"{{{{{key}}}}}"
            value = self.text_replacements[key]
            for run in paragraph.runs:
                if placeholder in run.text:
                    cnt = run.text.count(placeholder)
                    counts[key] += cnt
                    run.text = run.text.replace(placeholder, value)

        # Estrategia 2: Si el placeholder sigue presente en paragraph.text (estaba dividido entre runs)
        current_p_text = paragraph.text
        remaining_keys = [k for k in keys_present if f"{{{{{k}}}}}" in current_p_text]

        if remaining_keys and paragraph.runs:
            for key in remaining_keys:
                placeholder = f"{{{{{key}}}}}"
                value = self.text_replacements[key]
                if placeholder in current_p_text:
                    cnt = current_p_text.count(placeholder)
                    counts[key] += cnt
                    current_p_text = current_p_text.replace(placeholder, value)

            # Poner todo el texto formateado en el primer run y vaciar los demás
            paragraph.runs[0].text = current_p_text
            for run in paragraph.runs[1:]:
                run.text = ""

        return counts

    def _process_text_frame(self, text_frame) -> Dict[str, int]:
        counts = {k: 0 for k in self.text_replacements.keys()}
        for paragraph in text_frame.paragraphs:
            p_counts = self._replace_in_paragraph(paragraph)
            for k, v in p_counts.items():
                counts[k] += v
        return counts

    def _process_shape_text(self, shape) -> Dict[str, int]:
        """
        Procesa de manera recursiva formas, grupos de formas y tablas.
        """
        counts = {k: 0 for k in self.text_replacements.keys()}

        # 1. Cuadros de texto o formas con texto
        if shape.has_text_frame:
            tf_counts = self._process_text_frame(shape.text_frame)
            for k, v in tf_counts.items():
                counts[k] += v

        # 2. Tablas
        elif shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    if cell.text_frame:
                        cell_counts = self._process_text_frame(cell.text_frame)
                        for k, v in cell_counts.items():
                            counts[k] += v

        # 3. Grupos de formas
        elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for subshape in shape.shapes:
                sub_counts = self._process_shape_text(subshape)
                for k, v in sub_counts.items():
                    counts[k] += v

        return counts

    def _process_slide_images(self, slide) -> Dict[str, int]:
        """
        Busca formas cuyo texto sea un placeholder de imagen {{clave_imagen}}
        y lo reemplaza por la imagen respetando dimensiones y posición.
        """
        report = {k: 0 for k in self.image_replacements.keys()}
        shapes_to_replace = []

        for shape in slide.shapes:
            if shape.has_text_frame:
                texto_forma = shape.text.strip()
                for key, img_path in self.image_replacements.items():
                    placeholder = f"{{{{{key}}}}}"
                    if texto_forma == placeholder:
                        shapes_to_replace.append((shape, img_path, key))
                        break

        for shape, img_path, key in shapes_to_replace:
            if not os.path.exists(img_path):
                print(f"⚠️ Advertencia: La imagen '{img_path}' para '{{{{{key}}}}}' no existe. Omitiendo.")
                continue

            x, y = shape.left, shape.top
            cx, cy = shape.width, shape.height

            # Eliminar la forma original
            sp = shape.element
            sp.getparent().remove(sp)

            # Agregar la imagen en la misma posición
            slide.shapes.add_picture(img_path, x, y, cx, cy)
            report[key] += 1

        return report

    def render(self, output_path: Union[str, Path], verbose: bool = True) -> Dict[str, Any]:
        """
        Ejecuta la sustitución completa de textos e imágenes y guarda la presentación resultante.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        text_report = {k: 0 for k in self.text_replacements.keys()}
        image_report = {k: 0 for k in self.image_replacements.keys()}

        for slide in self.prs.slides:
            # 1. Reemplazo de texto (cuadros de texto, tablas, grupos)
            for shape in slide.shapes:
                shape_counts = self._process_shape_text(shape)
                for k, v in shape_counts.items():
                    text_report[k] += v

            # 2. Reemplazo de imágenes
            slide_img_counts = self._process_slide_images(slide)
            for k, v in slide_img_counts.items():
                image_report[k] += v

        self.prs.save(str(output_path))

        if verbose:
            print(f"✅ Presentación guardada en: {output_path}")
            
            # Resumen de reemplazos de texto
            encontrados_txt = [k for k, v in text_report.items() if v > 0]
            no_encontrados_txt = [k for k, v in text_report.items() if v == 0]
            print(f"  📝 Textos: {len(encontrados_txt)} variables reemplazadas.")
            if no_encontrados_txt:
                print(f"     ⚠️ Variables no encontradas ({len(no_encontrados_txt)}): {', '.join([f'{{{{{k}}}}}' for k in no_encontrados_txt[:10]])}" + 
                      (f" y {len(no_encontrados_txt)-10} más..." if len(no_encontrados_txt) > 10 else ""))

            # Resumen de reemplazos de imagen
            encontrados_img = [k for k, v in image_report.items() if v > 0]
            no_encontrados_img = [k for k, v in image_report.items() if v == 0]
            if self.image_replacements:
                print(f"  🖼️ Imágenes: {len(encontrados_img)} imágenes reemplazadas.")
                if no_encontrados_img:
                    print(f"     ⚠️ Imágenes no encontradas ({len(no_encontrados_img)}): {', '.join([f'{{{{{k}}}}}' for k in no_encontrados_img])}")

        return {
            "output_path": output_path,
            "text_report": text_report,
            "image_report": image_report
        }


# ─────────────────────────────────────────────────────────────────────────────
_EMU_POR_CM = 914400 / 2.54


def dimensiones_placeholder(template_path: Union[str, Path], clave: str,
                            unidad: str = "cm") -> Tuple[float, float]:
    """`(ancho, alto)` del cuadro de texto que contiene el marcador `{{clave}}`.

    `_process_slide_images` inserta la imagen con `add_picture(..., cx, cy)`,
    es decir forzando ANCHO y ALTO de la caja. Si la figura se generó con otra
    proporción, PowerPoint la estira y el texto sale deformado. Generándola con
    las medidas que devuelve esta función, llenar la caja no deforma nada.

    Leer la plantilla en vez de escribir las medidas a mano también evita que
    se desincronicen: si alguien mueve o redimensiona el cuadro en el PPTX, la
    siguiente corrida se ajusta sola.

    `unidad` acepta "cm" (lo que piden las funciones de `1_funciones/`),
    "in" o "emu".
    """
    factores = {"cm": _EMU_POR_CM, "in": 914400.0, "emu": 1.0}
    if unidad not in factores:
        raise ValueError(f"unidad '{unidad}' no reconocida; usa {sorted(factores)}.")

    ruta = Path(template_path)
    if not ruta.exists():
        raise FileNotFoundError(f"La plantilla PPTX no existe: {ruta}")

    objetivo = f"{{{{{clave}}}}}"
    encontrados = []

    def _buscar(shapes):
        for shape in shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                _buscar(shape.shapes)
            elif shape.has_text_frame and shape.text.strip() == objetivo:
                encontrados.append(shape)

    for slide in Presentation(str(ruta)).slides:
        _buscar(slide.shapes)

    if not encontrados:
        raise KeyError(
            f"'{objetivo}' no aparece como cuadro de texto en {ruta.name}. "
            f"El marcador debe ser TODO el texto de la forma, sin nada alrededor."
        )
    if len(encontrados) > 1:
        # Con varias cajas del mismo marcador la imagen entraría en todas con
        # medidas distintas; se avisa y se toma la primera.
        print(f"⚠️ '{objetivo}' aparece en {len(encontrados)} formas de "
              f"{ruta.name}; se toman las medidas de la primera.")

    f = factores[unidad]
    forma = encontrados[0]
    return forma.width / f, forma.height / f
