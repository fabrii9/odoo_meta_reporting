#!/usr/bin/env python3
"""
Descarga publicaciones y copy de una cuenta de Instagram.

ADVERTENCIA: Usar solo para contenido de tu propiedad. El scraping masivo o no
autorizado de terceros viola los Términos de Servicio de Instagram y puede
resultar en bloqueo de cuenta o IP.

Requiere:
    pip install -r requirements.txt

Uso:
    python instagram_downloader.py <username> --login <tu_usuario>

El script pedirá la contraseña de forma interactiva. Si la cuenta objetivo es
pública, no es estrictamente necesario iniciar sesión, pero Instagram suele
bloquear requests anónimos rápidamente.
"""

import argparse
import csv
import getpass
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    PleaseWaitFewMinutes,
    RateLimitError,
    TwoFactorRequired,
)


def eprint(*args, **kwargs):
    """Imprime en stderr."""
    print(*args, file=sys.stderr, **kwargs)


def get_env_or_prompt(env_var: str, prompt: str, secret: bool = False) -> str:
    """Obtiene un valor de una variable de entorno o lo pide por consola."""
    value = os.environ.get(env_var)
    if value:
        return value
    if secret:
        return getpass.getpass(prompt)
    return input(prompt)


def login_client(username: str, password: str | None = None, session_dir: Path = Path(".sessions")) -> Client:
    """
    Inicia sesión en Instagram reutilizando una sesión guardada si existe.
    Si no, hace login con usuario/contraseña y guarda la sesión.
    """
    session_dir.mkdir(exist_ok=True)
    session_file = session_dir / f"{username}.json"

    cl = Client()
    # Aumenta delays para no levantar sospechas
    cl.delay_range = [2, 5]

    if session_file.exists():
        eprint(f"[INFO] Reutilizando sesión guardada: {session_file}")
        try:
            cl.load_settings(str(session_file))
            cl.login(username, password or "")
            cl.get_timeline_feed()  # Verifica que la sesión siga activa
            return cl
        except LoginRequired:
            eprint("[WARN] Sesión expirada, se requiere login de nuevo.")
            session_file.unlink(missing_ok=True)
        except Exception as exc:
            eprint(f"[WARN] No se pudo cargar la sesión: {exc}")
            session_file.unlink(missing_ok=True)

    if not password:
        password = getpass.getpass(f"Contraseña para {username}: ")

    try:
        cl.login(username, password)
    except TwoFactorRequired:
        code = input("Instagram requiere 2FA. Ingresá el código: ").strip()
        cl.two_factor_login(code)

    cl.dump_settings(str(session_file))
    eprint(f"[INFO] Sesión guardada en {session_file}")
    return cl


def safe_filename(text: str, max_length: int = 80) -> str:
    """Devuelve un nombre de archivo seguro a partir de un texto."""
    if not text:
        return "sin_titulo"
    safe = "".join(c for c in text if c.isalnum() or c in (" ", "-", "_")).rstrip()
    safe = safe.replace(" ", "_")
    return safe[:max_length]


def download_media(cl: Client, media, base_folder: Path) -> list[Path]:
    """
    Descarga el archivo multimedia de un post.
    Soporta fotos, videos y álbumes (carruseles).
    """
    downloaded_paths: list[Path] = []

    try:
        if media.media_type == 1:  # Foto
            path = cl.photo_download(media.pk, folder=str(base_folder))
            downloaded_paths.append(Path(path))
        elif media.media_type == 2:  # Video / Reel
            path = cl.video_download(media.pk, folder=str(base_folder))
            downloaded_paths.append(Path(path))
        elif media.media_type == 8:  # Álbum / Carrusel
            paths = cl.album_download(media.pk, folder=str(base_folder))
            downloaded_paths.extend(Path(p) for p in paths)
        else:
            eprint(f"[WARN] Tipo de medio desconocido: {media.media_type}")
    except Exception as exc:
        eprint(f"[ERROR] Falló la descarga del post {media.pk}: {exc}")

    return downloaded_paths


def fetch_posts(cl: Client | None, username: str, output_dir: Path, only_public: bool = False) -> list[dict]:
    """
    Obtiene las publicaciones de un usuario y descarga su contenido.
    Devuelve una lista de diccionarios con metadata + copy.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    media_dir = output_dir / "media"
    media_dir.mkdir(exist_ok=True)

    eprint(f"[INFO] Obteniendo publicaciones de @{username}...")

    if cl:
        user_id = cl.user_id_from_username(username)
        medias = cl.user_medias(user_id, amount=0)
    else:
        # Intento anónimo (muy limitado, suele fallar rápido)
        cl = Client()
        cl.delay_range = [2, 5]
        user_id = cl.user_id_from_username(username)
        medias = cl.user_medias(user_id, amount=0)

    eprint(f"[INFO] Se encontraron {len(medias)} publicaciones.")

    records: list[dict] = []
    for idx, media in enumerate(reversed(medias), start=1):
        eprint(f"[INFO] Procesando {idx}/{len(medias)} - {media.pk}")

        try:
            downloaded = download_media(cl, media, media_dir)
            # Pequeña pausa entre posts
            time.sleep(2)

            record = {
                "index": idx,
                "post_id": str(media.pk),
                "shortcode": media.code,
                "url": f"https://instagram.com/p/{media.code}/",
                "caption": media.caption_text or "",
                "caption_hashtags": media.caption_hashtags or [],
                "caption_mentions": media.caption_mentions or [],
                "media_type": media.media_type,
                "taken_at": media.taken_at.isoformat() if media.taken_at else None,
                "like_count": media.like_count,
                "comment_count": media.comment_count,
                "downloaded_files": [str(p.relative_to(output_dir)) for p in downloaded],
            }
            records.append(record)

            # Guardado progresivo: un JSON por post (útil si se corta)
            post_json = output_dir / "posts" / f"{idx:04d}_{media.pk}.json"
            post_json.parent.mkdir(exist_ok=True)
            with open(post_json, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        except (RateLimitError, PleaseWaitFewMinutes) as exc:
            eprint(f"[ERROR] Rate limit alcanzado: {exc}")
            eprint("[INFO] Guardando progreso y saliendo. Volvé a correr el script en unas horas.")
            break
        except Exception as exc:
            eprint(f"[ERROR] No se pudo procesar {media.pk}: {exc}")
            continue

    return records


def save_manifest(records: list[dict], output_dir: Path, username: str) -> None:
    """Guarda el manifest.json y un resumen CSV."""
    manifest = {
        "username": username,
        "downloaded_at": datetime.now().isoformat(),
        "total_posts": len(records),
        "posts": records,
    }

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    eprint(f"[INFO] Manifest guardado en {manifest_path}")

    csv_path = output_dir / "posts_summary.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "index",
                "post_id",
                "shortcode",
                "url",
                "caption",
                "taken_at",
                "like_count",
                "comment_count",
                "downloaded_files",
            ],
        )
        writer.writeheader()
        for record in records:
            row = record.copy()
            row["downloaded_files"] = "; ".join(row["downloaded_files"])
            row["caption"] = row["caption"].replace("\n", " ")
            row["caption_hashtags"] = ", ".join(row.get("caption_hashtags", []))
            row["caption_mentions"] = ", ".join(row.get("caption_mentions", []))
            writer.writerow(row)
    eprint(f"[INFO] Resumen CSV guardado en {csv_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Descarga publicaciones y copy de una cuenta de Instagram."
    )
    parser.add_argument("username", help="Usuario de Instagram objetivo (sin @).")
    parser.add_argument(
        "--login",
        dest="login_user",
        help="Tu usuario de Instagram para iniciar sesión. Si no se pasa, se intenta acceso anónimo (muy limitado).",
    )
    parser.add_argument(
        "--output",
        default="downloads",
        help="Carpeta base de salida (default: downloads).",
    )
    parser.add_argument(
        "--no-media",
        action="store_true",
        help="Descargar solo metadata/copy, sin archivos multimedia.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output) / args.username
    output_dir.mkdir(parents=True, exist_ok=True)

    cl: Client | None = None
    if args.login_user:
        password = os.environ.get("INSTAGRAM_PASSWORD")
        cl = login_client(args.login_user, password)
    else:
        eprint(
            "[WARN] No se proporcionó usuario de login. El acceso anónimo a Instagram "
            "suele fallar rápidamente por rate limits."
        )

    records = fetch_posts(cl, args.username, output_dir)
    save_manifest(records, output_dir, args.username)

    print(f"\n✅ Listo. Se descargaron {len(records)} publicaciones en: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
