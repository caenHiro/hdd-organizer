"""
Subcategorías para imágenes descargadas (01b_imagenes/).

Heurísticas deterministas basadas en nombre y ruta — sin IA ni modelos.
Para clasificación avanzada con CLIP ver workspaces/organizar-fotos.
"""
from .subcategorias import detectar_subcategoria, SUBCARPETAS_IMAGEN

__all__ = ["detectar_subcategoria", "SUBCARPETAS_IMAGEN"]
