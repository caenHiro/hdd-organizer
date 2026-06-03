import csv
import json
import struct
import zlib
from pathlib import Path
import pytest
from src.organizador_hdd.paso7 import (
    homologar_nombre, generar_reporte, ejecutar_renombrado,
    _necesita_renombrar, _eliminar_emojis, _detectar_causa,
    generar_reporte_exif, ejecutar_renombrado_exif, _extraer_fecha_exif,
)


class TestHomologarNombre:
    # Cirílico
    def test_cirilico_a_latino(self):
        assert homologar_nombre("Иванов") == "Ivanov"

    def test_nombre_sin_cambio(self):
        assert homologar_nombre("cancion_2024") == "cancion_2024"

    # Caracteres decorativos
    def test_elimina_exclamaciones(self):
        resultado = homologar_nombre("cancion!!!")
        assert "!!!" not in resultado

    def test_elimina_emoji_texto(self):
        resultado = homologar_nombre("foto=)")
        assert "=)" not in resultado

    def test_elimina_copia(self):
        resultado = homologar_nombre("documento - copia")
        assert "copia" not in resultado.lower()

    def test_elimina_copy(self):
        resultado = homologar_nombre("file - Copy")
        assert "copy" not in resultado.lower()

    # Fechas
    def test_normaliza_fecha_dmy(self):
        assert homologar_nombre("foto_01-06-2024") == "foto_2024-06-01"

    def test_normaliza_fecha_dmy_barra(self):
        assert homologar_nombre("img_15/03/2023") == "img_2023-03-15"

    def test_fecha_ymd_sin_cambio(self):
        assert homologar_nombre("foto_2024-06-01") == "foto_2024-06-01"

    # Separadores
    def test_colapsa_guiones_multiples(self):
        assert "--" not in homologar_nombre("archivo---nombre")

    def test_colapsa_subrayados_multiples(self):
        assert "__" not in homologar_nombre("archivo___nombre")

    def test_recorta_extremos(self):
        resultado = homologar_nombre("  _archivo_  ")
        assert not resultado.startswith(" ")
        assert not resultado.startswith("_")
        assert not resultado.endswith("_")

    # Combinado
    def test_combinado_cirilico_fecha_basura(self):
        # "Иванов_01-06-2024!!!" → "Ivanov_2024-06-01"
        resultado = homologar_nombre("Иванов_01-06-2024!!!")
        assert "Ivanov" in resultado
        assert "2024-06-01" in resultado
        assert "!!!" not in resultado

    def test_nombre_vacio_devuelve_placeholder(self):
        assert homologar_nombre("") == "_archivo"
        assert homologar_nombre("   ") == "_archivo"


class TestEliminarEmojis:
    def test_elimina_emoji_clasico(self):
        assert "📸" not in _eliminar_emojis("foto📸2024")

    def test_elimina_emoji_bandera(self):
        assert "🇲🇽" not in _eliminar_emojis("viaje🇲🇽cancun")

    def test_elimina_multiples_emojis(self):
        resultado = _eliminar_emojis("🎌anime🎬pelicula")
        assert "🎌" not in resultado
        assert "🎬" not in resultado
        assert "anime" in resultado
        assert "pelicula" in resultado

    def test_sin_emojis_no_cambia(self):
        assert _eliminar_emojis("foto_2024") == "foto_2024"

    def test_homologar_nombre_quita_emoji(self):
        resultado = homologar_nombre("foto📸2024")
        assert "📸" not in resultado
        assert "foto" in resultado
        assert "2024" in resultado


class TestDetectarCausa:
    def test_cirilico(self):
        assert _detectar_causa("Иванов", "Ivanov") == "cirilico"

    def test_emoji(self):
        assert _detectar_causa("foto📸", "foto") == "emoji"

    def test_basura(self):
        assert _detectar_causa("archivo!!!", "archivo") == "basura"

    def test_fecha(self):
        assert _detectar_causa("img_01-06-2024", "img_2024-06-01") == "fecha"

    def test_separadores(self):
        assert _detectar_causa("archivo__nombre", "archivo_nombre") == "separadores"


class TestStatsResultado:
    def test_stats_por_causa(self, tmp_path):
        (tmp_path / "Иванов.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "foto📸.png").write_bytes(b"\x89PNG")
        (tmp_path / "archivo!!!.txt").write_text("x")
        resultado = generar_reporte(tmp_path)
        stats = resultado.stats_por_causa
        assert sum(stats.values()) == 3
        assert "cirilico" in stats or "combinado" in stats


class TestNecesitaRenombrar:
    def test_nombre_limpio_no_necesita(self):
        assert not _necesita_renombrar("foto_2024-01-01")

    def test_nombre_con_cirilico_necesita(self):
        assert _necesita_renombrar("Иванов")

    def test_nombre_con_exclamaciones_necesita(self):
        assert _necesita_renombrar("archivo!!!")


class TestGenerarReporte:
    def test_propone_cambios(self, tmp_path):
        (tmp_path / "Иванов.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "foto!!!.png").write_bytes(b"\x89PNG")
        resultado = generar_reporte(tmp_path)
        assert resultado.total_cambios == 2

    def test_no_propone_si_limpio(self, tmp_path):
        (tmp_path / "foto_limpia.jpg").write_bytes(b"\xff\xd8")
        resultado = generar_reporte(tmp_path)
        assert resultado.total_cambios == 0

    def test_escribe_csv(self, tmp_path):
        (tmp_path / "Иванов.jpg").write_bytes(b"\xff\xd8")
        csv_path = tmp_path / "reporte.csv"
        generar_reporte(tmp_path, ruta_csv=csv_path)
        assert csv_path.exists()
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            filas = list(reader)
        assert len(filas) == 1
        assert filas[0]["nombre_nuevo"] == "Ivanov.jpg"

    def test_csv_tiene_cabecera(self, tmp_path):
        (tmp_path / "Ж.jpg").write_bytes(b"\xff\xd8")
        csv_path = tmp_path / "r.csv"
        generar_reporte(tmp_path, ruta_csv=csv_path)
        contenido = csv_path.read_text(encoding="utf-8")
        assert "nombre_original" in contenido
        assert "nombre_nuevo" in contenido


class TestEjecutarRenombrado:
    def test_dry_run_no_renombra(self, tmp_path):
        orig = tmp_path / "Иванов.jpg"
        orig.write_bytes(b"\xff\xd8")
        resultado = generar_reporte(tmp_path)
        ejec = ejecutar_renombrado(resultado, tmp_path / "log.json", dry_run=True)
        assert orig.exists()
        assert len(ejec.renombrados) == 1

    def test_real_renombra(self, tmp_path):
        orig = tmp_path / "Иванов.jpg"
        orig.write_bytes(b"\xff\xd8")
        resultado = generar_reporte(tmp_path)
        ejec = ejecutar_renombrado(resultado, tmp_path / "log.json", dry_run=False)
        assert not orig.exists()
        assert (tmp_path / "Ivanov.jpg").exists()
        assert len(ejec.renombrados) == 1

    def test_escribe_log_con_paso_7(self, tmp_path):
        (tmp_path / "foto!!!.jpg").write_bytes(b"\xff\xd8")
        resultado = generar_reporte(tmp_path)
        log = tmp_path / "log.json"
        ejecutar_renombrado(resultado, log, dry_run=False)
        datos = json.loads(log.read_text())
        assert datos["paso"] == 7
        assert len(datos["renombrados"]) == 1

    def test_log_reversible(self, tmp_path):
        """El log tiene nombre_nuevo como origen y nombre_original como destino."""
        (tmp_path / "Иванов.jpg").write_bytes(b"\xff\xd8")
        resultado = generar_reporte(tmp_path)
        log = tmp_path / "log.json"
        ejecutar_renombrado(resultado, log, dry_run=False)
        datos = json.loads(log.read_text())
        mov = datos["renombrados"][0]
        assert mov["origen"] == "Ivanov.jpg"
        assert mov["destino"] == "Иванов.jpg"

    def test_colision_añade_sufijo(self, tmp_path):
        (tmp_path / "Иванов.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "Ivanov.jpg").write_bytes(b"existente")  # colisión
        resultado = generar_reporte(tmp_path)
        ejec = ejecutar_renombrado(resultado, tmp_path / "log.json", dry_run=False)
        assert len(ejec.renombrados) == 1
        nuevo = ejec.renombrados[0]["nuevo"]
        assert "_2" in nuevo


# ─── EXIF tests ───────────────────────────────────────────────────────────────

def _make_jpeg_with_exif(path: Path, datetime_str: str) -> None:
    """Crea un JPEG mínimo con etiqueta EXIF DateTimeOriginal."""
    try:
        from PIL import Image
        import piexif
        img = Image.new("RGB", (1, 1), color=(255, 255, 255))
        exif_dict = {"Exif": {piexif.ExifIFD.DateTimeOriginal: datetime_str.encode()}}
        exif_bytes = piexif.dump(exif_dict)
        img.save(str(path), "JPEG", exif=exif_bytes)
    except ImportError:
        # Pillow o piexif no disponibles — crear JPEG mínimo sin EXIF
        path.write_bytes(b"\xff\xd8\xff\xd9")


class TestExifRename:
    def test_exif_sin_exif_skip(self, tmp_path):
        (tmp_path / "foto.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        resultado = generar_reporte_exif(tmp_path)
        assert resultado.sin_exif == 1
        assert resultado.total_cambios == 0

    def test_exif_ya_con_fecha_skip(self, tmp_path):
        (tmp_path / "2024-03-15_foto.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        resultado = generar_reporte_exif(tmp_path)
        assert resultado.ya_con_fecha == 1
        assert resultado.total_cambios == 0

    def test_no_foto_skip(self, tmp_path):
        (tmp_path / "documento.pdf").write_bytes(b"%PDF")
        resultado = generar_reporte_exif(tmp_path)
        assert resultado.no_es_foto >= 1
        assert resultado.total_cambios == 0

    def test_exif_reporte_genera_propuesta(self, tmp_path):
        f = tmp_path / "mi_foto.jpg"
        _make_jpeg_with_exif(f, "2024:06:15 14:30:22")
        resultado = generar_reporte_exif(tmp_path)
        if resultado.sin_exif == 1:
            pytest.skip("Pillow/piexif no disponibles para EXIF test")
        assert resultado.total_cambios == 1
        p = resultado.propuestas[0]
        assert p.nombre_original == "mi_foto.jpg"
        assert "2024-06-15" in p.nombre_nuevo
        assert "143022" in p.nombre_nuevo

    def test_exif_dry_run_no_renombra(self, tmp_path):
        f = tmp_path / "foto_sin_fecha.jpg"
        _make_jpeg_with_exif(f, "2023:12:01 09:00:00")
        resultado = generar_reporte_exif(tmp_path)
        if resultado.sin_exif == 1:
            pytest.skip("Pillow/piexif no disponibles")
        ejec = ejecutar_renombrado_exif(resultado, tmp_path / "log.json", dry_run=True)
        assert f.exists()
        assert len(ejec.renombrados) == resultado.total_cambios

    def test_exif_confirmar_renombra(self, tmp_path):
        f = tmp_path / "foto_sin_fecha.jpg"
        _make_jpeg_with_exif(f, "2025:01:20 18:45:00")
        resultado = generar_reporte_exif(tmp_path)
        if resultado.sin_exif == 1:
            pytest.skip("Pillow/piexif no disponibles")
        ejec = ejecutar_renombrado_exif(resultado, tmp_path / "log.json", dry_run=False)
        assert not f.exists()
        assert len(ejec.renombrados) == 1
        nuevo = tmp_path / ejec.renombrados[0]["nuevo"]
        assert nuevo.exists()
        assert "2025-01-20" in nuevo.name

    def test_exif_csv_generado(self, tmp_path):
        f = tmp_path / "foto.jpg"
        _make_jpeg_with_exif(f, "2024:03:10 12:00:00")
        csv_path = tmp_path / "reporte.csv"
        resultado = generar_reporte_exif(tmp_path, ruta_csv=csv_path)
        if resultado.sin_exif == 1:
            pytest.skip("Pillow/piexif no disponibles")
        assert csv_path.exists()
        import csv as _csv
        rows = list(_csv.reader(csv_path.open()))
        assert rows[0] == ["carpeta", "nombre_original", "nombre_nuevo", "fecha_exif"]
        assert len(rows) > 1
