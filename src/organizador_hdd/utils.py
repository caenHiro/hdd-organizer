"""Utilidades compartidas entre pasos: sanitización de nombres, transliteración, hash."""
import hashlib
import re

_HASH_CHUNK = 65536  # 64 KB — suficiente para detectar contenido distinto en archivos grandes


def hash_rapido(ruta: "Path", chunk: int = _HASH_CHUNK) -> str:
    """SHA256 de los primeros `chunk` bytes del archivo."""
    h = hashlib.sha256()
    try:
        from pathlib import Path as _P
        with open(ruta, "rb") as f:
            h.update(f.read(chunk))
    except OSError:
        return ""
    return h.hexdigest()


def mismo_contenido(origen: "Path", destino: "Path") -> bool:
    """True si ambos archivos tienen el mismo tamaño y hash rápido."""
    try:
        if origen.stat().st_size != destino.stat().st_size:
            return False
    except OSError:
        return False
    return hash_rapido(origen) == hash_rapido(destino)


def resolver_destino(origen: "Path", destino_base: "Path") -> "Path | None":
    """
    Calcula el destino final para mover `origen`.
    - None  → omitir: el archivo ya existe en destino con mismo contenido (idempotente)
    - Path  → destino resuelto (con sufijo _2, _3 si hay colisión de nombre con distinto contenido)
    """
    from pathlib import Path
    destino_base = Path(destino_base)
    if not destino_base.exists():
        return destino_base
    if mismo_contenido(Path(origen), destino_base):
        return None
    stem, suffix = destino_base.stem, destino_base.suffix
    i = 2
    ruta = destino_base
    while ruta.exists():
        ruta = destino_base.parent / f"{stem}_{i}{suffix}"
        i += 1
    return ruta

# ISO 9:1995 / GOST 7.79-2000 — Cirílico → Latino
_CIRILICO_ISO9: dict[str, str] = {
    'А': 'A',  'Б': 'B',  'В': 'V',  'Г': 'G',  'Д': 'D',
    'Е': 'E',  'Ё': 'Yo', 'Ж': 'Zh', 'З': 'Z',  'И': 'I',
    'Й': 'J',  'К': 'K',  'Л': 'L',  'М': 'M',  'Н': 'N',
    'О': 'O',  'П': 'P',  'Р': 'R',  'С': 'S',  'Т': 'T',
    'У': 'U',  'Ф': 'F',  'Х': 'X',  'Ц': 'C',  'Ч': 'Ch',
    'Ш': 'Sh', 'Щ': 'Shh','Ъ': '',   'Ы': 'Y',  'Ь': '',
    'Э': 'E',  'Ю': 'Yu', 'Я': 'Ya',
    'а': 'a',  'б': 'b',  'в': 'v',  'г': 'g',  'д': 'd',
    'е': 'e',  'ё': 'yo', 'ж': 'zh', 'з': 'z',  'и': 'i',
    'й': 'j',  'к': 'k',  'л': 'l',  'м': 'm',  'н': 'n',
    'о': 'o',  'п': 'p',  'р': 'r',  'с': 's',  'т': 't',
    'у': 'u',  'ф': 'f',  'х': 'x',  'ц': 'c',  'ч': 'ch',
    'ш': 'sh', 'щ': 'shh','ъ': '',   'ы': 'y',  'ь': '',
    'э': 'e',  'ю': 'yu', 'я': 'ya',
    # Ucraniano
    'І': 'I',  'і': 'i',  'Ї': 'Yi', 'ї': 'yi', 'Є': 'Ye', 'є': 'ye',
    'Ґ': 'G',  'ґ': 'g',
}

# Caracteres inválidos en nombres de archivo (Windows + Unix)
_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Puntos o espacios al final (Windows no los permite)
_TRAILING = re.compile(r'[\s.]+$')


def transliterar(texto: str) -> str:
    """Convierte caracteres cirílicos a Latino usando ISO 9. Deja el resto intacto."""
    return "".join(_CIRILICO_ISO9.get(c, c) for c in texto)


def sanitizar_nombre(nombre: str, max_len: int = 200) -> str:
    """
    Sanitiza un string para usarlo como nombre de carpeta o archivo:
    - Transliteración cirílica
    - Elimina caracteres inválidos en sistemas de archivos
    - Elimina puntos/espacios finales
    - Recorta a max_len caracteres
    """
    resultado = transliterar(nombre)
    resultado = _INVALIDOS.sub("_", resultado)
    resultado = _TRAILING.sub("", resultado)
    resultado = resultado.strip()
    if not resultado:
        resultado = "_sin_nombre"
    return resultado[:max_len]


def resolver_colision(ruta_base) -> "Path":
    """Si ruta_base existe, devuelve ruta con sufijo _2, _3, etc."""
    from pathlib import Path
    ruta = Path(ruta_base)
    if not ruta.exists():
        return ruta
    stem = ruta.stem
    suffix = ruta.suffix
    i = 2
    while ruta.exists():
        ruta = ruta.parent / f"{stem}_{i}{suffix}"
        i += 1
    return ruta


def contar_paginas_pdf(ruta: "Path") -> int | None:
    """Devuelve el número de páginas de un PDF. None si pypdf no está disponible o hay error."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(ruta)).pages)
    except Exception:
        return None


def _cargar_patrones_privados() -> frozenset[str]:
    import json
    config_path = __file__.replace("utils.py", "config.json")
    try:
        with open(config_path, encoding="utf-8") as f:
            datos = json.load(f)
        return frozenset(p.lower() for p in datos.get("carpetas_privadas", {}).get("patrones", []))
    except Exception:
        return frozenset({"_privado", "privado", "privados"})


_PATRONES_PRIVADOS: frozenset[str] = _cargar_patrones_privados()


def es_carpeta_privada(ruta: "Path", patrones: frozenset[str] | None = None) -> bool:
    """True si alguna parte de la ruta (carpeta padre) coincide con un patrón privado."""
    from pathlib import Path
    patrones = patrones or _PATRONES_PRIVADOS
    for parte in Path(ruta).parts:
        if parte.lower() in patrones:
            return True
    return False


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
