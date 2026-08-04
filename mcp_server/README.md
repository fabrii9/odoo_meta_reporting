# Servidor MCP — Meta Ads Reporting

Servidor MCP (Model Context Protocol) que expone los datos de Meta Ads
almacenados en BigQuery como herramientas para modelos de IA. Permite
preguntarle a un modelo (Claude, etc.) cosas como "¿cómo rindieron las
campañas esta semana?" y que responda con datos reales.

## Herramientas disponibles

| Tool | Descripción |
|---|---|
| `get_kpis` | Gasto, impresiones, clics, CTR, CPC, CPM, alcance, frecuencia + conversiones |
| `get_daily_metrics` | Serie diaria con CTR/CPC/CPM/ROAS (tendencias) |
| `get_campaigns` | Rendimiento por campaña con ROAS |
| `get_adsets` | Rendimiento por conjunto de anuncios |
| `get_ads` | Rendimiento por anuncio con estado e imagen del creativo |
| `get_funnel` | Embudo completo con costo por paso |
| `get_placements` | Distribución por plataforma (facebook, instagram, etc.) |

Todas aceptan `date_from` / `date_to` (YYYY-MM-DD, opcionales — default
últimos 7 días) y algunas `campaign_name` (filtro opcional, nombre exacto).

## Instalación

```bash
cd mcp_server
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Configuración

Variables de entorno:

| Variable | Descripción | Default |
|---|---|---|
| `META_BQ_PROJECT_ID` | Proyecto de GCP/BigQuery | (requerida) |
| `META_BQ_DATASET` | Dataset | `meta_ads` |
| `META_BQ_TABLE_PREFIX` | Prefijo de tablas | `daily_` |
| `META_BQ_CREDENTIALS_FILE` | Ruta al JSON de service account | (requerida) |
| `META_MCP_TRANSPORT` | `stdio` o `http` | `stdio` |
| `META_MCP_HOST` | Host modo http | `127.0.0.1` |
| `META_MCP_PORT` | Puerto modo http | `8100` |

## Opción A — Local (stdio, Claude Desktop)

En `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "meta-ads": {
      "command": "/ruta/al/repo/mcp_server/venv/bin/python",
      "args": ["/ruta/al/repo/mcp_server/mcp_server.py"],
      "env": {
        "META_BQ_PROJECT_ID": "tu-proyecto-gcp",
        "META_BQ_CREDENTIALS_FILE": "/ruta/al/service-account.json"
      }
    }
  }
}
```

## Opción B — Remoto (HTTP en el servidor)

```bash
META_MCP_TRANSPORT=http \
META_MCP_HOST=127.0.0.1 \
META_MCP_PORT=8100 \
META_BQ_PROJECT_ID=tu-proyecto-gcp \
META_BQ_CREDENTIALS_FILE=/ruta/al/service-account.json \
./venv/bin/python mcp_server.py
```

Queda escuchando en `http://127.0.0.1:8100/mcp` (streamable HTTP).

Para conectarte desde tu máquina sin exponerlo públicamente:

```bash
ssh -L 8100:127.0.0.1:8100 root@tu-servidor
```

y en el cliente MCP apuntar a `http://localhost:8100/mcp`.

> El modo HTTP no incluye autenticación propia: mantenerlo en localhost
> (túnel SSH) o ponerlo detrás de nginx con autenticación.

## systemd (producción)

Ver `meta-ads-mcp.service` de ejemplo en este directorio.
