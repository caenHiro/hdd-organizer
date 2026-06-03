"""
clasificador_clip.py — Clasificación semántica de imágenes con OpenAI CLIP.

Categoriza fotos en subcarpetas usando embeddings de texto/imagen.
Mucho más preciso que heurísticas de nombre de archivo.

Requisitos (pesados — instalar solo cuando se use):
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    pip install git+https://github.com/openai/CLIP.git

Categorías disponibles:
    wallpaper, arte_digital, autos, memes, casa_hogar, personas,
    naturaleza_plantas, animales_reptiles, tecnologia, comida, otro

Uso programático:
    from organizador_hdd.clasificador_clip import ClasificadorCLIP
    clf = ClasificadorCLIP()
    categoria = clf.clasificar(Path("foto.jpg"))

Uso desde CLI:
    hdd-organizar clasificar-clip /directorio/fotos --mover
    hdd-organizar clasificar-clip /directorio/fotos --dry-run
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

_EXT_FOTO = frozenset({
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".tiff", ".tif", ".bmp", ".webp",
})

CATEGORIAS: dict[str, list[str]] = {
    "wallpaper": [
        "a desktop wallpaper with abstract pattern",
        "a landscape wallpaper for computer screen",
        "an artistic background image",
    ],
    "arte_digital": [
        "digital art illustration",
        "anime artwork or manga drawing",
        "fan art or concept art",
        "pixel art or vector illustration",
    ],
    "autos": [
        "a car or automobile",
        "a motorcycle or vehicle",
        "a racing car or sports car",
    ],
    "memes": [
        "an internet meme with text",
        "a funny screenshot or joke image",
        "a reaction image with caption",
    ],
    "casa_hogar": [
        "interior design or furniture",
        "a room, kitchen or living room",
        "home decor or architecture",
    ],
    "personas": [
        "a person or people",
        "a portrait or selfie",
        "a group of people",
    ],
    "naturaleza_plantas": [
        "a cactus or succulent plant",
        "a flower or garden",
        "nature landscape with trees",
        "a plant or vegetation",
    ],
    "animales_reptiles": [
        "a reptile snake or lizard",
        "a boa constrictor or python",
        "an iguana or gecko",
        "a pet animal",
    ],
    "tecnologia": [
        "computer hardware or electronics",
        "a circuit board or motherboard",
        "a smartphone or laptop",
        "programming code on a screen",
    ],
    "comida": [
        "food or meal",
        "a dish or beverage",
        "cooking ingredients",
    ],
    "otro": [
        "a miscellaneous photo",
    ],
}


@dataclass
class ResultadoCLIP:
    clasificados: list[dict] = field(default_factory=list)
    errores: list[dict] = field(default_factory=list)
    omitidos: int = 0

    @property
    def total(self) -> int:
        return len(self.clasificados)


class ClasificadorCLIP:
    """Clasificador semántico de imágenes usando OpenAI CLIP."""

    def __init__(self, modelo: str = "ViT-B/32", dispositivo: str | None = None):
        try:
            import clip
            import torch
        except ImportError as e:
            raise ImportError(
                "Instalar dependencias: pip install torch torchvision && "
                "pip install git+https://github.com/openai/CLIP.git"
            ) from e

        import torch as _torch
        self._torch = _torch
        self._clip = clip
        self.device = dispositivo or ("cuda" if _torch.cuda.is_available() else "cpu")
        self.model, self.preprocess = clip.load(modelo, device=self.device)
        self.model.eval()

        # Pre-computar embeddings de texto por categoría
        todos_prompts = []
        self._cat_indices: dict[str, tuple[int, int]] = {}
        idx = 0
        for cat, prompts in CATEGORIAS.items():
            self._cat_indices[cat] = (idx, idx + len(prompts))
            todos_prompts.extend(prompts)
            idx += len(prompts)

        tokens = clip.tokenize(todos_prompts).to(self.device)
        with _torch.no_grad():
            self._text_features = self.model.encode_text(tokens)
            self._text_features /= self._text_features.norm(dim=-1, keepdim=True)

    def clasificar(self, ruta: Path, umbral_confianza: float = 0.0) -> tuple[str, float]:
        """
        Clasifica una imagen.
        Retorna (categoria, confianza_0_a_1).
        confianza < umbral_confianza → retorna ("otro", confianza).
        """
        try:
            from PIL import Image
            imagen = Image.open(ruta).convert("RGB")
            img_tensor = self.preprocess(imagen).unsqueeze(0).to(self.device)

            with self._torch.no_grad():
                img_feat = self.model.encode_image(img_tensor)
                img_feat /= img_feat.norm(dim=-1, keepdim=True)

            sims = (img_feat @ self._text_features.T).squeeze(0)

            # Máximo por categoría (promediar prompts)
            cat_scores: dict[str, float] = {}
            for cat, (inicio, fin) in self._cat_indices.items():
                cat_scores[cat] = float(sims[inicio:fin].mean())

            mejor_cat = max(cat_scores, key=lambda c: cat_scores[c])
            confianza = cat_scores[mejor_cat]

            if confianza < umbral_confianza:
                return "otro", confianza
            return mejor_cat, confianza

        except Exception as e:
            return "otro", 0.0

    def clasificar_directorio(
        self,
        directorio: str | Path,
        destino: str | Path | None = None,
        mover: bool = False,
        dry_run: bool = True,
        umbral: float = 0.0,
    ) -> ResultadoCLIP:
        """
        Clasifica todas las imágenes de un directorio.
        Si mover=True: mueve a subdirectorios por categoría.
        Si dry_run=True: solo reporta, no mueve.
        """
        directorio = Path(directorio)
        destino    = Path(destino) if destino else directorio
        resultado  = ResultadoCLIP()

        fotos = [
            f for f in directorio.rglob("*")
            if f.is_file() and f.suffix.lower() in _EXT_FOTO
        ]

        print(f"Clasificando {len(fotos)} imágenes con CLIP [{self.device}]...")

        for i, ruta in enumerate(fotos):
            categoria, confianza = self.clasificar(ruta, umbral)
            destino_dir = destino / categoria

            info = {
                "ruta_original": str(ruta),
                "nombre": ruta.name,
                "categoria": categoria,
                "confianza": round(confianza, 4),
                "destino": str(destino_dir / ruta.name),
                "movido": False,
            }

            if mover and not dry_run:
                destino_dir.mkdir(parents=True, exist_ok=True)
                destino_final = destino_dir / ruta.name
                if destino_final.exists():
                    stem, ext = ruta.stem, ruta.suffix
                    k = 2
                    while destino_final.exists():
                        destino_final = destino_dir / f"{stem}_{k}{ext}"
                        k += 1
                try:
                    shutil.move(str(ruta), str(destino_final))
                    info["destino"] = str(destino_final)
                    info["movido"] = True
                except OSError as e:
                    resultado.errores.append({"ruta": str(ruta), "error": str(e)})
                    continue

            resultado.clasificados.append(info)

            if (i + 1) % 10 == 0 or (i + 1) == len(fotos):
                print(f"  [{i+1}/{len(fotos)}] {ruta.name} → {categoria} ({confianza:.2f})")

        return resultado
