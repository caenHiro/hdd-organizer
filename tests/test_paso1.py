import json
import shutil
from pathlib import Path

import pytest

from src.organizador_hdd.paso1 import (
    Artefacto,
    ResultadoPaso1,
    detectar_artefactos,
    construir_plan,
    ejecutar_plan,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _crear_arbol(tmp_path: Path) -> Path:
    """
    Crea un árbol de directorios con artefactos y archivos legítimos mezclados:

    hdd/
    ├── proyecto_java/
    │   ├── src/Main.java          ← legítimo
    │   └── target/
    │       └── Main.class         ← artefacto (carpeta 'target' con .class)
    ├── proyecto_web/
    │   ├── index.html             ← legítimo
    │   └── node_modules/
    │       └── lodash/index.js    ← artefacto (carpeta 'node_modules')
    ├── .m2/
    │   └── repository/
    │       └── artifact.pom       ← artefacto (carpeta .m2/repository)
    ├── scripts/
    │   ├── util.py                ← legítimo
    │   └── __pycache__/
    │       └── util.cpython-312.pyc ← artefacto (carpeta __pycache__)
    ├── backup/
    │   └── foto.jpg               ← legítimo
    ├── checksums.sha1             ← artefacto (extensión)
    ├── Thumbs.db                  ← artefacto (nombre exacto)
    └── documento.pdf              ← legítimo
    """
    hdd = tmp_path / "hdd"
    hdd.mkdir()

    # proyecto java con target
    (hdd / "proyecto_java" / "src").mkdir(parents=True)
    (hdd / "proyecto_java" / "src" / "Main.java").write_text("class Main {}")
    (hdd / "proyecto_java" / "target").mkdir()
    (hdd / "proyecto_java" / "target" / "Main.class").write_bytes(b"\xca\xfe\xba\xbe")

    # proyecto web con node_modules
    (hdd / "proyecto_web").mkdir()
    (hdd / "proyecto_web" / "index.html").write_text("<html/>")
    (hdd / "proyecto_web" / "node_modules" / "lodash").mkdir(parents=True)
    (hdd / "proyecto_web" / "node_modules" / "lodash" / "index.js").write_text("module.exports={}")

    # maven .m2/repository
    (hdd / ".m2" / "repository").mkdir(parents=True)
    (hdd / ".m2" / "repository" / "artifact.pom").write_text("<project/>")

    # __pycache__
    (hdd / "scripts").mkdir()
    (hdd / "scripts" / "util.py").write_text("pass")
    (hdd / "scripts" / "__pycache__").mkdir()
    (hdd / "scripts" / "__pycache__" / "util.cpython-312.pyc").write_bytes(b"\x00\x00")

    # backup legítimo
    (hdd / "backup").mkdir()
    (hdd / "backup" / "foto.jpg").write_bytes(b"\xff\xd8\xff")

    # artefactos sueltos
    (hdd / "checksums.sha1").write_text("abc123")
    (hdd / "Thumbs.db").write_bytes(b"\x00")

    # legítimo suelto
    (hdd / "documento.pdf").write_bytes(b"%PDF")

    return hdd


# ─── Detección ────────────────────────────────────────────────────────────────

class TestDetectarArtefactos:
    def test_detecta_extension_sha1(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "checksums.sha1").write_text("abc")
        resultado = detectar_artefactos(hdd)
        assert resultado.total_archivos == 1
        assert resultado.archivos[0].razon == "extension"

    def test_detecta_nombre_exacto_thumbs(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "Thumbs.db").write_bytes(b"\x00")
        resultado = detectar_artefactos(hdd)
        assert resultado.total_archivos == 1
        assert resultado.archivos[0].razon == "nombre_exacto"

    def test_detecta_carpeta_node_modules(self, tmp_path):
        hdd = tmp_path / "hdd"
        (hdd / "node_modules" / "lib").mkdir(parents=True)
        (hdd / "node_modules" / "lib" / "index.js").write_text("x")
        resultado = detectar_artefactos(hdd)
        assert any(c.name == "node_modules" for c in resultado.carpetas)

    def test_detecta_carpeta_pycache(self, tmp_path):
        hdd = tmp_path / "hdd"
        (hdd / "pkg" / "__pycache__").mkdir(parents=True)
        (hdd / "pkg" / "__pycache__" / "mod.pyc").write_bytes(b"\x00")
        resultado = detectar_artefactos(hdd)
        assert any(c.name == "__pycache__" for c in resultado.carpetas)

    def test_detecta_target_con_class(self, tmp_path):
        hdd = tmp_path / "hdd"
        (hdd / "target").mkdir(parents=True)
        (hdd / "target" / "App.class").write_bytes(b"\xca\xfe")
        resultado = detectar_artefactos(hdd)
        assert any(c.name == "target" for c in resultado.carpetas)

    def test_no_marca_target_sin_class(self, tmp_path):
        hdd = tmp_path / "hdd"
        (hdd / "target").mkdir(parents=True)
        (hdd / "target" / "output.txt").write_text("datos")
        resultado = detectar_artefactos(hdd)
        assert not any(c.name == "target" for c in resultado.carpetas)

    def test_detecta_m2_repository(self, tmp_path):
        hdd = tmp_path / "hdd"
        (hdd / ".m2" / "repository" / "org").mkdir(parents=True)
        (hdd / ".m2" / "repository" / "org" / "lib.jar").write_bytes(b"PK")
        resultado = detectar_artefactos(hdd)
        assert any(c.name == "repository" for c in resultado.carpetas)

    def test_no_itera_dentro_de_node_modules(self, tmp_path):
        """El scanner no debe reportar archivos sueltos dentro de carpetas marcadas."""
        hdd = tmp_path / "hdd"
        (hdd / "node_modules" / "pkg").mkdir(parents=True)
        # Este .sha1 está DENTRO de node_modules — no debe aparecer como archivo suelto
        (hdd / "node_modules" / "pkg" / "hash.sha1").write_text("abc")
        resultado = detectar_artefactos(hdd)
        assert resultado.total_archivos == 0
        assert len(resultado.carpetas) == 1

    def test_no_detecta_archivos_legitimos(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "foto.jpg").write_bytes(b"\xff\xd8")
        (hdd / "doc.pdf").write_bytes(b"%PDF")
        (hdd / "main.py").write_text("pass")
        resultado = detectar_artefactos(hdd)
        assert resultado.total_archivos == 0
        assert len(resultado.carpetas) == 0

    def test_arbol_completo(self, tmp_path):
        hdd = _crear_arbol(tmp_path)
        resultado = detectar_artefactos(hdd)
        # Carpetas marcadas: target, node_modules, .m2/repository, __pycache__
        assert len(resultado.carpetas) == 4
        # Archivos sueltos: checksums.sha1, Thumbs.db
        assert resultado.total_archivos == 2
        # Legítimos NO detectados: Main.java, index.html, util.py, foto.jpg, documento.pdf
        rutas = [str(a.ruta) for a in resultado.archivos]
        assert not any("foto.jpg" in r for r in rutas)
        assert not any("documento.pdf" in r for r in rutas)


# ─── ResultadoPaso1 helpers ───────────────────────────────────────────────────

class TestResultadoPaso1:
    def test_total_bytes_suma_artefactos(self, tmp_path):
        r = ResultadoPaso1()
        r.archivos = [
            Artefacto(ruta=tmp_path / "a.sha1", razon="extension", tamanio=100),
            Artefacto(ruta=tmp_path / "b.class", razon="extension", tamanio=200),
        ]
        assert r.total_bytes == 300

    def test_por_extension_agrupa(self, tmp_path):
        r = ResultadoPaso1()
        r.archivos = [
            Artefacto(ruta=tmp_path / "a.sha1", razon="extension", tamanio=10),
            Artefacto(ruta=tmp_path / "b.sha1", razon="extension", tamanio=10),
            Artefacto(ruta=tmp_path / "c.class", razon="extension", tamanio=10),
        ]
        ext = r.por_extension()
        assert ext[".sha1"] == 2
        assert ext[".class"] == 1


# ─── Plan ─────────────────────────────────────────────────────────────────────

class TestConstruirPlan:
    def test_plan_incluye_archivos_y_carpetas(self, tmp_path):
        hdd = _crear_arbol(tmp_path)
        resultado = detectar_artefactos(hdd)
        destino = tmp_path / "artefactos"
        plan = construir_plan(resultado, destino)
        # 4 carpetas + 2 archivos sueltos
        assert len(plan) == 6

    def test_destinos_bajo_carpeta_correcta(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "f.sha1").write_text("abc")
        resultado = detectar_artefactos(hdd)
        destino = tmp_path / "artefactos"
        plan = construir_plan(resultado, destino)
        assert plan.movimientos[0]["destino"].startswith(str(destino / "archivos"))

    def test_colision_añade_sufijo(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "f.sha1").write_text("abc")
        resultado = detectar_artefactos(hdd)
        destino = tmp_path / "artefactos"
        # Crear archivo destino para forzar colisión
        (destino / "archivos").mkdir(parents=True)
        (destino / "archivos" / "f.sha1").write_text("existente")
        plan = construir_plan(resultado, destino)
        assert plan.movimientos[0]["destino"].endswith("f_2.sha1")


# ─── Ejecución ────────────────────────────────────────────────────────────────

class TestEjecutarPlan:
    def test_dry_run_no_mueve(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "f.sha1").write_text("abc")
        resultado = detectar_artefactos(hdd)
        plan = construir_plan(resultado, tmp_path / "dest")
        ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=True)
        assert len(ejec.movidos) == 1
        assert (hdd / "f.sha1").exists()  # sigue en origen

    def test_dry_run_no_crea_log(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "f.sha1").write_text("abc")
        resultado = detectar_artefactos(hdd)
        plan = construir_plan(resultado, tmp_path / "dest")
        log = tmp_path / "log.json"
        ejecutar_plan(plan, log, dry_run=True)
        assert not log.exists()

    def test_real_mueve_archivo(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "f.sha1").write_text("abc")
        resultado = detectar_artefactos(hdd)
        destino = tmp_path / "artefactos"
        plan = construir_plan(resultado, destino)
        log = tmp_path / "logs" / "reversion.json"
        ejec = ejecutar_plan(plan, log, dry_run=False)
        assert not (hdd / "f.sha1").exists()
        assert (destino / "archivos" / "f.sha1").exists()
        assert len(ejec.movidos) == 1
        assert len(ejec.errores) == 0

    def test_real_escribe_log_antes_de_mover(self, tmp_path):
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "f.class").write_bytes(b"\xca\xfe")
        resultado = detectar_artefactos(hdd)
        destino = tmp_path / "artefactos"
        plan = construir_plan(resultado, destino)
        log = tmp_path / "logs" / "reversion.json"
        ejecutar_plan(plan, log, dry_run=False)
        assert log.exists()
        datos = json.loads(log.read_text())
        assert datos["paso"] == 1
        assert len(datos["movimientos"]) == 1

    def test_log_permite_reversion(self, tmp_path):
        """El log tiene origen/destino invertidos para poder deshacer con ejecutar_plan."""
        hdd = tmp_path / "hdd"
        hdd.mkdir()
        (hdd / "f.sha1").write_text("abc")
        resultado = detectar_artefactos(hdd)
        destino = tmp_path / "artefactos"
        plan = construir_plan(resultado, destino)
        log = tmp_path / "logs" / "reversion.json"
        ejecutar_plan(plan, log, dry_run=False)

        datos = json.loads(log.read_text())
        # El log de reversión tiene origen = donde está ahora, destino = donde estaba
        mov = datos["movimientos"][0]
        assert str(destino / "archivos" / "f.sha1") == mov["origen"]
        assert str(hdd / "f.sha1") == mov["destino"]


# ─── Idempotencia ─────────────────────────────────────────────────────────────

def test_idempotente_mismo_contenido_omite(tmp_path):
    """Si el archivo ya está en destino con mismo contenido → se omite, no se mueve."""
    hdd = tmp_path / "hdd"
    hdd.mkdir()
    origen = hdd / "f.class"
    origen.write_bytes(b"\xca\xfe\xba\xbe")

    destino = tmp_path / "artefactos"
    (destino / "archivos").mkdir(parents=True)
    (destino / "archivos" / "f.class").write_bytes(b"\xca\xfe\xba\xbe")

    resultado = detectar_artefactos(hdd)
    plan = construir_plan(resultado, destino)

    assert len(plan.movimientos) == 0
    assert len(plan.omitidos_identicos) == 1
    assert str(origen) in plan.omitidos_identicos


def test_idempotente_contenido_distinto_usa_sufijo(tmp_path):
    """Si el nombre existe pero el contenido es diferente → sufijo _2."""
    hdd = tmp_path / "hdd"
    hdd.mkdir()
    origen = hdd / "f.class"
    origen.write_bytes(b"\x00\x01\x02\x03")

    destino = tmp_path / "artefactos"
    (destino / "archivos").mkdir(parents=True)
    (destino / "archivos" / "f.class").write_bytes(b"\xff\xfe\xfd\xfc")

    resultado = detectar_artefactos(hdd)
    plan = construir_plan(resultado, destino)

    assert len(plan.movimientos) == 1
    assert plan.movimientos[0]["destino"].endswith("f_2.class")
    assert len(plan.omitidos_identicos) == 0


def test_idempotente_omitidos_en_resultado_ejecucion(tmp_path):
    """Los omitidos_identicos del plan se propagan al ResultadoEjecucion."""
    hdd = tmp_path / "hdd"
    hdd.mkdir()
    contenido = b"\xca\xfe" * 100
    (hdd / "f.class").write_bytes(contenido)

    destino = tmp_path / "artefactos"
    (destino / "archivos").mkdir(parents=True)
    (destino / "archivos" / "f.class").write_bytes(contenido)

    resultado = detectar_artefactos(hdd)
    plan = construir_plan(resultado, destino)
    ejec = ejecutar_plan(plan, tmp_path / "log.json", dry_run=True)

    assert len(ejec.omitidos_identicos) == 1
