# Instagram Downloader

Script para descargar publicaciones, reels, fotos, videos y **copy/caption** de una cuenta de Instagram de forma ordenada.

> ⚠️ **ADVERTENCIA LEGAL Y ÉTICA**
> Usá esta herramienta **únicamente para contenido de tu propiedad** o para el que tengas permiso explícito. Instagram prohíbe el scraping masivo no autorizado en sus Términos de Servicio. El uso indebido puede resultar en:
> - Bloqueo temporal o permanente de la cuenta.
> - Restricciones de IP.
> - Acciones legales por parte del titular del contenido.

---

## Qué descarga

- Fotos, videos y álbumes/carruseles en `downloads/<username>/media/`
- Metadata de cada post en `downloads/<username>/posts/<id>.json`
- Manifest completo en `downloads/<username>/manifest.json`
- Resumen CSV en `downloads/<username>/posts_summary.csv` (ideal para leer el copy en Excel/Google Sheets)

---

## Instalación

```bash
# Activar el entorno virtual existente
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

---

## Uso

### Con login (recomendado)

```bash
python instagram_downloader.py TU_CUENTA_ORIGEN --login TU_USUARIO
```

Ejemplo:

```bash
python instagram_downloader.py mi_negocio_2023 --login mi_negocio
```

Te pedirá la contraseña de forma interactiva. También podés pasarla por variable de entorno:

```bash
export INSTAGRAM_PASSWORD="tu_contraseña"
python instagram_downloader.py mi_negocio_2023 --login mi_negocio
```

### Sin login (muy limitado)

```bash
python instagram_downloader.py USUARIO_PUBLICO
```

Instagram suele bloquear rápidamente las requests anónimas, así que no es recomendable para más de unas pocas publicaciones.

---

## Estructura de salida

```
downloads/
└── mi_negocio_2023/
    ├── manifest.json
    ├── posts_summary.csv
    ├── posts/
    │   ├── 0001_123456789.json
    │   ├── 0002_987654321.json
    │   └── ...
    └── media/
        ├── foto_1.jpg
        ├── video_2.mp4
        └── ...
```

---

## Campos del CSV

| Campo | Descripción |
|-------|-------------|
| `index` | Orden de publicación (1 es la más antigua) |
| `post_id` | ID interno de Instagram |
| `shortcode` | Código corto de la URL (`instagram.com/p/{shortcode}`) |
| `url` | Link directo al post |
| `caption` | Texto/copy completo de la publicación |
| `taken_at` | Fecha y hora de publicación (ISO 8601) |
| `like_count` | Cantidad de likes |
| `comment_count` | Cantidad de comentarios |
| `downloaded_files` | Archivos descargados separados por `;` |

---

## Precauciones para no ser bloqueado

1. **No corras el script varias veces seguidas** en poco tiempo.
2. **No uses una cuenta personal importante** como login; si Instagram detecta comportamiento automatizado, puede pedir verificación.
3. El script ya incluye pausas entre publicaciones (2-5 segundos) y sesiones persistentes.
4. Si ves un error de rate limit, esperá varias horas antes de volver a intentar.

---

## Solución de problemas

### "challenge_required" / "suspicious login attempt"

Instagram pidió verificación. Iniciá sesión manualmente desde el navegador o la app, resolvé el desafío y borrá el archivo de sesión:

```bash
rm .sessions/TU_USUARIO.json
```

Luego volvé a correr el script.

### Two-Factor Authentication (2FA)

El script te pedirá el código 2FA en la primera ejecución. Una vez guardada la sesión, no lo volverá a pedir.

### "Please wait a few minutes"

Rate limit. Pará la ejecución y esperá al menos 1-2 horas. El script guarda el progreso hasta donde llegó.

---

## Alternativa oficial

Si solo necesitás un backup de tu cuenta, Instagram permite descargar todos tus datos:

1. Andá a **Configuración → Cuenta → Descargar tu información**.
2. Pedí el archivo en formato JSON.
3. En unas horas/días recibís un ZIP con todo tu contenido y metadatos.

Esa vía es más segura, aunque menos conveniente si querés re-publicar en otra cuenta.
