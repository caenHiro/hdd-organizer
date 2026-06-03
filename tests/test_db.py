import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import pytest
from src.analizador.db import BaseDatos
from src.analizador.scanner import ArchivoInfo


def _info(ruta: str, nombre: str, tipo: str = "imagen", tamanio: int = 1024,
          hash_sha256: str = "", dias_atras: int = 0) -> ArchivoInfo:
    fecha = datetime.now() - timedelta(days=dias_atras)
    return ArchivoInfo(
        ruta=ruta, nombre=nombre, extension=Path(nombre).suffix,
        tipo=tipo, tamanio=tamanio, fecha_modificacion=fecha,
        hash_sha256=hash_sha256,
    )


@pytest.fixture
def db_poblada(tmp_path):
    db = BaseDatos(str(tmp_path / "test.db"))
    lote = [
        _info("/fotos/img1.jpg", "img1.jpg", "imagen", 2 * 1024 * 1024, "aaa", dias_atras=400),
        _info("/fotos/img2.jpg", "img2.jpg", "imagen", 3 * 1024 * 1024, "bbb", dias_atras=10),
        _info("/docs/doc1.pdf", "doc1.pdf", "documento", 500 * 1024, "ccc", dias_atras=200),
        _info("/docs/doc2.pdf", "doc2.pdf", "documento", 1 * 1024 * 1024, "aaa", dias_atras=5),
        _info("/video/pelicula.mp4", "pelicula.mp4", "video", 700 * 1024 * 1024, "ddd", dias_atras=300),
    ]
    db.insertar_lote(lote)
    return db


class TestBuscarPorTipo:
    def test_encuentra_imagenes(self, db_poblada):
        resultado = db_poblada.buscar_por_tipo("imagen")
        assert len(resultado) == 2
        assert all(r["tipo"] == "imagen" for r in resultado)

    def test_encuentra_documentos(self, db_poblada):
        resultado = db_poblada.buscar_por_tipo("documento")
        assert len(resultado) == 2

    def test_tipo_inexistente_retorna_vacio(self, db_poblada):
        resultado = db_poblada.buscar_por_tipo("ejecutable")
        assert resultado == []

    def test_min_bytes_filtra(self, db_poblada):
        resultado = db_poblada.buscar_por_tipo("imagen", min_bytes=3 * 1024 * 1024)
        assert len(resultado) == 1
        assert resultado[0]["nombre"] == "img2.jpg"


class TestBuscarPorExtension:
    def test_encuentra_pdfs(self, db_poblada):
        resultado = db_poblada.buscar_por_extension(".pdf")
        assert len(resultado) == 2

    def test_sin_punto_funciona(self, db_poblada):
        resultado = db_poblada.buscar_por_extension("pdf")
        assert len(resultado) == 2

    def test_extension_mayuscula(self, db_poblada):
        resultado = db_poblada.buscar_por_extension(".PDF")
        assert len(resultado) == 2

    def test_extension_inexistente(self, db_poblada):
        resultado = db_poblada.buscar_por_extension(".xyz")
        assert resultado == []


class TestArchivosViejos:
    def test_encuentra_viejos(self, db_poblada):
        resultado = db_poblada.archivos_viejos("/fotos", dias=180)
        assert len(resultado) == 1
        assert resultado[0]["nombre"] == "img1.jpg"

    def test_directorio_sin_archivos(self, db_poblada):
        resultado = db_poblada.archivos_viejos("/inexistente", dias=180)
        assert resultado == []

    def test_min_bytes_filtra(self, db_poblada):
        resultado = db_poblada.archivos_viejos("/docs", dias=100, min_bytes=600 * 1024)
        assert len(resultado) == 0  # doc1.pdf tiene 500KB < 600KB


class TestArchivosPorFecha:
    def test_sin_filtro_retorna_todos(self, db_poblada):
        resultado = db_poblada.archivos_por_fecha()
        assert len(resultado) == 5

    def test_filtro_desde(self, db_poblada):
        hace_50 = (datetime.now() - timedelta(days=50)).date().isoformat()
        resultado = db_poblada.archivos_por_fecha(desde=hace_50)
        # img2.jpg (10d), doc2.pdf (5d) deberían estar dentro
        nombres = {r["nombre"] for r in resultado}
        assert "img2.jpg" in nombres
        assert "doc2.pdf" in nombres
        assert "pelicula.mp4" not in nombres

    def test_filtro_hasta(self, db_poblada):
        hace_250 = (datetime.now() - timedelta(days=250)).date().isoformat()
        resultado = db_poblada.archivos_por_fecha(hasta=hace_250)
        nombres = {r["nombre"] for r in resultado}
        assert "img1.jpg" in nombres
        assert "pelicula.mp4" in nombres
        assert "img2.jpg" not in nombres


class TestExportarCSV:
    def test_exporta_todos(self, db_poblada, tmp_path):
        csv_path = str(tmp_path / "out.csv")
        total = db_poblada.exportar_csv(csv_path)
        assert total == 5
        contenido = Path(csv_path).read_text(encoding="utf-8")
        assert "img1.jpg" in contenido
        assert "pelicula.mp4" in contenido

    def test_crea_archivo(self, db_poblada, tmp_path):
        csv_path = str(tmp_path / "inventario.csv")
        db_poblada.exportar_csv(csv_path)
        assert Path(csv_path).exists()

    def test_tiene_cabecera(self, db_poblada, tmp_path):
        csv_path = str(tmp_path / "out.csv")
        db_poblada.exportar_csv(csv_path)
        primera_linea = Path(csv_path).read_text().splitlines()[0]
        assert "nombre" in primera_linea
        assert "ruta" in primera_linea
        assert "tamanio" in primera_linea
