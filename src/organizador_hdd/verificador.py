"""
Verificación de integridad de archivos por tipo.

Usa las mismas librerías opcionales que el resto del pipeline:
  imágenes → Pillow
  audio    → mutagen
  PDFs     → pypdf
  ZIPs     → zipfile (stdlib)
  otros    → lectura completa sin errores de I/O

Si la librería no está disponible, el archivo se considera OK (no se penaliza).
"""
from pathlib import Path


def verificar_imagen(ruta: Path) -> tuple[bool, str]:
    try:
        from PIL import Image
        with Image.open(ruta) as img:
            img.verify()
        return True, ""
    except ImportError:
        return True, ""
    except Exception as e:
        return False, str(e)


def verificar_audio(ruta: Path) -> tuple[bool, str]:
    try:
        import mutagen
        f = mutagen.File(str(ruta))
        if f is None:
            return False, "mutagen no reconoce el formato"
        return True, ""
    except ImportError:
        return True, ""
    except Exception as e:
        return False, str(e)


def verificar_pdf(ruta: Path) -> tuple[bool, str]:
    try:
        from pypdf import PdfReader
        PdfReader(str(ruta))
        return True, ""
    except ImportError:
        return True, ""
    except Exception as e:
        return False, str(e)


def verificar_zip(ruta: Path) -> tuple[bool, str]:
    """Verifica la integridad de un ZIP usando la CRC de cada entrada."""
    import zipfile
    try:
        with zipfile.ZipFile(ruta, "r") as zf:
            resultado = zf.testzip()
            if resultado is not None:
                return False, f"entrada corrupta: {resultado}"
        return True, ""
    except zipfile.BadZipFile as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def verificar_generico(ruta: Path) -> tuple[bool, str]:
    """Intenta leer el archivo completo para detectar errores de I/O o truncamiento."""
    try:
        with open(ruta, "rb") as f:
            while f.read(65536):
                pass
        return True, ""
    except Exception as e:
        return False, str(e)


_EXT_IMAGEN = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
                          ".webp", ".heic", ".heif"})
_EXT_AUDIO  = frozenset({".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".opus", ".wma"})
_EXT_PDF    = frozenset({".pdf"})
_EXT_ZIP    = frozenset({".zip", ".cbz"})


def verificar_archivo(ruta: Path) -> tuple[bool, str]:
    """
    Verifica la integridad del archivo según su extensión.
    Devuelve (ok, motivo_error).
    """
    ext = ruta.suffix.lower()
    if ext in _EXT_IMAGEN:
        return verificar_imagen(ruta)
    if ext in _EXT_AUDIO:
        return verificar_audio(ruta)
    if ext in _EXT_PDF:
        return verificar_pdf(ruta)
    if ext in _EXT_ZIP:
        return verificar_zip(ruta)
    return verificar_generico(ruta)


def _codificar_ruta(ruta: Path, base: Path) -> str:
    """
    Convierte una ruta en una cadena segura para usar como nombre de carpeta,
    usando '__' como separador de directorio.

    Ejemplo:
      ruta: /respaldo/01_fotos/2024/01_enero/foto.jpg  (o su padre)
      base: /respaldo
      → "01_fotos__2024__01_enero"
    """
    try:
        rel = ruta.relative_to(base)
        return "__".join(rel.parts) if rel.parts else "_raiz"
    except ValueError:
        return ruta.name or "_raiz"


def ruta_danado(ruta_destino_intendida: Path, base_hdd: Path) -> Path:
    """
    Genera la ruta de destino para un archivo dañado.

    Codifica el directorio destino intendido como nombre de subcarpeta dentro de
    _pendientes/dañados/ para permitir la recuperación.

    Ejemplo:
      intendida: /respaldo/01_fotos/2024/01_enero/foto.jpg
      base_hdd:  /respaldo
      resultado: /respaldo/_pendientes/dañados/01_fotos__2024__01_enero/foto.jpg
    """
    carpeta_encoded = _codificar_ruta(ruta_destino_intendida.parent, base_hdd)
    return base_hdd / "_pendientes" / "dañados" / carpeta_encoded / ruta_destino_intendida.name


# Alias para compatibilidad interna — preferir ruta_danado en código nuevo
def ruta_revision(ruta_destino_intendida: Path, base_hdd: Path) -> Path:
    return ruta_danado(ruta_destino_intendida, base_hdd)
