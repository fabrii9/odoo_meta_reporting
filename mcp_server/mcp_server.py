# -*- coding: utf-8 -*-
"""
Servidor MCP para Meta Ads Reporting.

Expone los datos de campañas de Meta Ads (almacenados en BigQuery por el
módulo de Odoo) como herramientas MCP, para que un modelo de IA pueda
consultarlos y generar reportes.

Configuración por variables de entorno:
    META_BQ_PROJECT_ID        (requerida) proyecto de GCP/BigQuery
    META_BQ_DATASET           dataset de BigQuery (default: meta_ads)
    META_BQ_TABLE_PREFIX      prefijo de tablas (default: daily_)
    META_BQ_CREDENTIALS_FILE  ruta al JSON de service account (requerida)
    META_MCP_TRANSPORT        stdio (default) | http
    META_MCP_HOST             host para http (default: 127.0.0.1)
    META_MCP_PORT             puerto para http (default: 8100)

Uso:
    python mcp_server.py                 # stdio (Claude Desktop local)
    META_MCP_TRANSPORT=http python mcp_server.py   # HTTP remoto
"""
import os
import sys
import json
import logging
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
_logger = logging.getLogger('meta-ads-mcp')

# Importar el servicio de queries del módulo Odoo (solo necesita google-cloud-bigquery)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'services'))
from bigquery_query_service import BigQueryQueryService  # noqa: E402

from fastmcp import FastMCP  # noqa: E402

PROJECT_ID = os.environ.get('META_BQ_PROJECT_ID', '').strip()
DATASET = os.environ.get('META_BQ_DATASET', 'meta_ads').strip()
TABLE_PREFIX = os.environ.get('META_BQ_TABLE_PREFIX', 'daily_').strip()
CREDENTIALS_FILE = os.environ.get('META_BQ_CREDENTIALS_FILE', '').strip()
TRANSPORT = os.environ.get('META_MCP_TRANSPORT', 'stdio').strip().lower()
HOST = os.environ.get('META_MCP_HOST', '127.0.0.1').strip()
PORT = int(os.environ.get('META_MCP_PORT', '8100'))

if not PROJECT_ID:
    raise SystemExit('Falta META_BQ_PROJECT_ID')
if not CREDENTIALS_FILE or not os.path.exists(CREDENTIALS_FILE):
    raise SystemExit('Falta META_BQ_CREDENTIALS_FILE o el archivo no existe: %s' % CREDENTIALS_FILE)

with open(CREDENTIALS_FILE) as f:
    _credentials_json = f.read()

_service = BigQueryQueryService(PROJECT_ID, _credentials_json)

mcp = FastMCP('meta-ads-reporting')


def _table_ref(level):
    mapping = {
        'campaign': 'campaign_stats',
        'adset': 'adset_stats',
        'ad': 'ad_stats',
    }
    return f"{PROJECT_ID}.{DATASET}.{TABLE_PREFIX}{mapping[level]}"


def _default_dates(date_from, date_to):
    """Si no pasan fechas, últimos 7 días."""
    if date_from and date_to:
        return date_from, date_to
    today = date.today()
    return (today - timedelta(days=7)).isoformat(), (today - timedelta(days=1)).isoformat()


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return round(value, 4)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _rows(data):
    if isinstance(data, dict):
        return {k: _clean(v) for k, v in data.items()}
    return [{k: _clean(v) for k, v in row.items()} for row in data]


@mcp.tool()
def get_kpis(date_from: str = '', date_to: str = '', campaign_name: str = '') -> str:
    """KPIs agregados de Meta Ads para un rango de fechas: gasto, impresiones,
    clics, CTR, CPC, CPM, alcance y frecuencia. Fechas en formato YYYY-MM-DD
    (si se omiten, últimos 7 días). campaign_name es opcional (nombre exacto)."""
    d_from, d_to = _default_dates(date_from, date_to)
    campaign = campaign_name or None
    kpis = _service.get_kpis(_table_ref('campaign'), d_from, d_to, campaign)
    conv = _service.get_conversion_kpis(_table_ref('campaign'), d_from, d_to, campaign)
    return json.dumps({
        'period': {'from': d_from, 'to': d_to},
        'kpis': _rows(kpis),
        'conversions': _rows(conv),
    }, ensure_ascii=False, indent=1)


@mcp.tool()
def get_daily_metrics(date_from: str = '', date_to: str = '', campaign_name: str = '') -> str:
    """Serie diaria de métricas de Meta Ads: gasto, impresiones, clics,
    CTR, CPC, CPM y ROAS ponderado por día. Útil para tendencias.
    Fechas YYYY-MM-DD (si se omiten, últimos 7 días)."""
    d_from, d_to = _default_dates(date_from, date_to)
    rows = _service.get_ratio_series(_table_ref('campaign'), d_from, d_to, campaign_name or None)
    return json.dumps(_rows(rows), ensure_ascii=False, indent=1)


@mcp.tool()
def get_campaigns(date_from: str = '', date_to: str = '') -> str:
    """Rendimiento agregado por campaña: gasto, impresiones, clics, CTR y ROAS.
    Fechas YYYY-MM-DD (si se omiten, últimos 7 días)."""
    d_from, d_to = _default_dates(date_from, date_to)
    rows = _service.get_campaigns(_table_ref('campaign'), d_from, d_to)
    return json.dumps(_rows(rows), ensure_ascii=False, indent=1)


@mcp.tool()
def get_adsets(date_from: str = '', date_to: str = '', campaign_name: str = '') -> str:
    """Rendimiento agregado por conjunto de anuncios (adset).
    Fechas YYYY-MM-DD (si se omiten, últimos 7 días). campaign_name opcional."""
    d_from, d_to = _default_dates(date_from, date_to)
    rows = _service.get_adsets(_table_ref('adset'), d_from, d_to, campaign_name or None)
    return json.dumps(_rows(rows), ensure_ascii=False, indent=1)


@mcp.tool()
def get_ads(date_from: str = '', date_to: str = '', campaign_name: str = '') -> str:
    """Rendimiento por anuncio individual, con estado (ACTIVE/PAUSED), compras,
    ROAS y URLs de imagen del creativo. Fechas YYYY-MM-DD (si se omiten,
    últimos 7 días). campaign_name opcional."""
    d_from, d_to = _default_dates(date_from, date_to)
    rows = _service.get_ads(_table_ref('ad'), d_from, d_to, campaign_name or None)
    return json.dumps(_rows(rows), ensure_ascii=False, indent=1)


@mcp.tool()
def get_funnel(date_from: str = '', date_to: str = '', campaign_name: str = '') -> str:
    """Embudo de conversión: impresiones, clics en enlace, visitas a la página,
    agregados al carrito, checkout iniciado y compras, con tasa de conversión
    y costo por paso. Fechas YYYY-MM-DD (si se omiten, últimos 7 días)."""
    d_from, d_to = _default_dates(date_from, date_to)
    steps = _service.get_funnel(_table_ref('campaign'), d_from, d_to, campaign_name or None)
    return json.dumps(_rows(steps), ensure_ascii=False, indent=1)


@mcp.tool()
def get_placements(date_from: str = '', date_to: str = '', campaign_name: str = '') -> str:
    """Distribución por plataforma (facebook, instagram, audience_network,
    threads, whatsapp): gasto, impresiones y clics por publisher_platform.
    Fechas YYYY-MM-DD (si se omiten, últimos 7 días)."""
    d_from, d_to = _default_dates(date_from, date_to)
    rows = _service.get_placements(_table_ref('campaign'), d_from, d_to, campaign_name or None)
    return json.dumps(_rows(rows), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    _logger.info('MCP Meta Ads: proyecto=%s dataset=%s transport=%s', PROJECT_ID, DATASET, TRANSPORT)
    if TRANSPORT == 'http':
        mcp.run(transport='http', host=HOST, port=PORT)
    else:
        mcp.run()
