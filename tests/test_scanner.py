import hashlib
import tempfile
from pathlib import Path
import pytest
from src.analizador.scanner import escanear_directorio, clasificar_tipo, calcular_hash, ArchivoInfo


def _crear_archivo(carpeta: Path, nombre: str, contenido: bytes) -> Path:
    p = carpeta / nombre
    p.write_bytes(contenido)
    return p


@pytest.fixture
def directorio_prueba(tmp_path):
    (tmp_path / "fotos").mkdir()
    (tmp_path / "docs").mkdir()
    _crear_archivo(tmp_path / "fotos", "foto1.jpg", b"fake-jpeg-content")
    _crear_archivo(tmp_path / "fotos", "foto2.png", b"fake-png-content")
    _crear_archivo(tmp_path / "docs", "informe.pdf", b"fake-pdf-content")
    _crear_archivo(tmp_path, "script.py", b"print('hola')")
    # Duplicado: mismo contenido que foto1.jpg
    _crear_archivo(tmp_path, "copia.jpg", b"fake-jpeg-content")
    return tmp_path


class TestClasificarTipo:
    def test_imagen(self):
        assert clasificar_tipo(".jpg") == "imagen"
        assert clasificar_tipo(".PNG") == "imagen"

    def test_video(self):
        assert clasificar_tipo(".mp4") == "video"

    def test_audio(self):
        assert clasificar_tipo(".mp3") == "audio"

    def test_documento(self):
        assert clasificar_tipo(".pdf") == "documento"

    def test_codigo(self):
        assert clasificar_tipo(".py") == "codigo"

    def test_desconocido(self):
        assert clasificar_tipo(".xyz") == "otro"


class TestCalcularHash:
    def test_hash_correcto(self, tmp_path):
        contenido = b"contenido de prueba"
        p = _crear_archivo(tmp_path, "prueba.txt", contenido)
        esperado = hashlib.sha256(contenido).hexdigest()
        assert calcular_hash(p) == esperado

    def test_mismo_contenido_mismo_hash(self, tmp_path):
        contenido = b"mismo contenido"
        p1 = _crear_archivo(tmp_path, "a.txt", contenido)
        p2 = _crear_archivo(tmp_path, "b.txt", contenido)
        assert calcular_hash(p1) == calcular_hash(p2)

    def test_diferente_contenido_diferente_hash(self, tmp_path):
        p1 = _crear_archivo(tmp_path, "a.txt", b"contenido A")
        p2 = _crear_archivo(tmp_path, "b.txt", b"contenido B")
        assert calcular_hash(p1) != calcular_hash(p2)

    def test_archivo_no_existente(self, tmp_path):
        assert calcular_hash(tmp_path / "noexiste.txt") == ""


class TestEscanearDirectorio:
    def test_encuentra_todos_los_archivos(self, directorio_prueba):
        archivos = list(escanear_directorio(str(directorio_prueba), calcular_hashes=False))
        assert len(archivos) == 5

    def test_retorna_archivoinfo(self, directorio_prueba):
        archivos = list(escanear_directorio(str(directorio_prueba), calcular_hashes=False))
        assert all(isinstance(a, ArchivoInfo) for a in archivos)

    def test_clasifica_tipos(self, directorio_prueba):
        archivos = {a.nombre: a.tipo for a in escanear_directorio(str(directorio_prueba), calcular_hashes=False)}
        assert archivos["foto1.jpg"] == "imagen"
        assert archivos["informe.pdf"] == "documento"
        assert archivos["script.py"] == "codigo"

    def test_calcula_hashes(self, directorio_prueba):
        archivos = {a.nombre: a for a in escanear_directorio(str(directorio_prueba), calcular_hashes=True)}
        assert archivos["foto1.jpg"].hash_sha256 != ""
        assert archivos["foto1.jpg"].hash_sha256 == archivos["copia.jpg"].hash_sha256

    def test_sin_hashes(self, directorio_prueba):
        archivos = list(escanear_directorio(str(directorio_prueba), calcular_hashes=False))
        assert all(a.hash_sha256 == "" for a in archivos)

    def test_no_modifica_archivos(self, directorio_prueba):
        contenido_antes = {
            p.name: p.read_bytes()
            for p in directorio_prueba.rglob("*")
            if p.is_file()
        }
        list(escanear_directorio(str(directorio_prueba)))
        contenido_despues = {
            p.name: p.read_bytes()
            for p in directorio_prueba.rglob("*")
            if p.is_file()
        }
        assert contenido_antes == contenido_despues

    def test_tamanio_correcto(self, directorio_prueba):
        archivos = {a.nombre: a for a in escanear_directorio(str(directorio_prueba), calcular_hashes=False)}
        assert archivos["script.py"].tamanio == len(b"print('hola')")

    def test_callback_se_invoca(self, directorio_prueba):
        vistos = []
        list(escanear_directorio(
            str(directorio_prueba),
            calcular_hashes=False,
            callback=lambda info: vistos.append(info.nombre),
        ))
        assert len(vistos) == 5
