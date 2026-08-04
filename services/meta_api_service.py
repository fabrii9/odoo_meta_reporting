# -*- coding: utf-8 -*-
import logging
import time
import hmac
import hashlib
import json
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

# Importaciones soft para evitar crash si no están instaladas
try:
    from facebook_business.api import FacebookAdsApi
    from facebook_business.adobjects.adaccount import AdAccount
    from facebook_business.adobjects.adsinsights import AdsInsights
    from facebook_business.exceptions import FacebookRequestError
except Exception as e:  # pragma: no cover
    _logger.warning("facebook_business no está instalado: %s", e)
    FacebookAdsApi = None
    AdAccount = None
    AdsInsights = None
    FacebookRequestError = Exception


class MetaApiService:
    def __init__(self, app_id, app_secret, access_token):
        if FacebookAdsApi is None:
            raise RuntimeError(
                "La librería 'facebook-business' no está instalada. "
                "Ejecute: pip install facebook-business"
            )
        self.app_id = (app_id or '').strip()
        self.app_secret = (app_secret or '').strip()
        self.access_token = (access_token or '').strip()
        self.appsecret_proof = self._generate_appsecret_proof(self.app_secret, self.access_token)
        self.api = FacebookAdsApi.init(
            app_id=app_id,
            app_secret=app_secret,
            access_token=access_token,
        )

    @staticmethod
    def _generate_appsecret_proof(app_secret, access_token):
        """Genera el appsecret_proof requerido por algunas apps de Meta."""
        if not app_secret or not access_token:
            return None
        return hmac.new(
            app_secret.encode('utf-8'),
            access_token.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

    def test_connection(self, account_id):
        """Verifica que la cuenta sea accesible."""
        account = AdAccount(f'act_{account_id}')
        fields = [AdsInsights.Field.account_id]
        params = {
            'date_preset': 'yesterday',
            'level': 'account',
        }
        if self.appsecret_proof:
            params['appsecret_proof'] = self.appsecret_proof
        # Llamada ligera para validar credenciales
        insights = account.get_insights(fields=fields, params=params)
        # Consumir el generador para forzar la llamada
        list(insights)
        return True

    def fetch_insights(self, account_id, date_from, date_to, level='campaign'):
        """
        Extrae insights de Meta para un rango de fechas y nivel.
        Retorna lista de dicts normalizados.
        """
        account = AdAccount(f'act_{account_id}')

        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.campaign_id,
            AdsInsights.Field.adset_name,
            AdsInsights.Field.adset_id,
            AdsInsights.Field.ad_name,
            AdsInsights.Field.ad_id,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.ctr,
            AdsInsights.Field.cpc,
            AdsInsights.Field.cpm,
            AdsInsights.Field.reach,
            AdsInsights.Field.frequency,
            AdsInsights.Field.actions,
            AdsInsights.Field.action_values,
            AdsInsights.Field.purchase_roas,
            AdsInsights.Field.cost_per_action_type,
            AdsInsights.Field.inline_link_clicks,
            AdsInsights.Field.inline_link_click_ctr,
            AdsInsights.Field.outbound_clicks,
            AdsInsights.Field.video_play_actions,
            AdsInsights.Field.video_p25_watched_actions,
            AdsInsights.Field.video_p50_watched_actions,
            AdsInsights.Field.video_p75_watched_actions,
            AdsInsights.Field.video_p100_watched_actions,
            AdsInsights.Field.date_start,
        ]

        # Rankings de calidad solo están disponibles a nivel anuncio
        if level == 'ad':
            fields += [
                AdsInsights.Field.quality_ranking,
                AdsInsights.Field.engagement_rate_ranking,
                AdsInsights.Field.conversion_rate_ranking,
            ]

        # Convertir fechas a string
        since = date_from.strftime('%Y-%m-%d') if hasattr(date_from, 'strftime') else str(date_from)
        until = date_to.strftime('%Y-%m-%d') if hasattr(date_to, 'strftime') else str(date_to)

        params = {
            'level': level,
            'time_increment': 1,
            'time_range': {'since': since, 'until': until},
        }
        if self.appsecret_proof:
            params['appsecret_proof'] = self.appsecret_proof

        _logger.info(
            'Meta API: fetch_insights account=%s level=%s since=%s until=%s',
            account_id, level, since, until,
        )

        insights = self._fetch_with_retry(account, fields, params)
        records = self._normalize_insights(insights, level)

        # Si es nivel 'ad', enriquecer con creative data (imágenes)
        if level == 'ad' and records:
            creative_map = self._fetch_creative_data(account_id, [r['ad_id'] for r in records if r.get('ad_id')])
            for record in records:
                ad_id = record.get('ad_id')
                if ad_id and ad_id in creative_map:
                    record.update(creative_map[ad_id])

        return records

    def _fetch_creative_data(self, account_id, ad_ids):
        """
        Obtiene creative data (thumbnails, imágenes) para una lista de ad_ids.
        Retorna dict {ad_id: {thumbnail_url, image_url, creative_type}}.
        """
        if not ad_ids:
            return {}

        # Eliminar duplicados y vacíos
        unique_ids = list(set([aid for aid in ad_ids if aid]))
        if not unique_ids:
            return {}

        account = AdAccount(f'act_{account_id}')
        creative_map = {}

        # La API de Meta permite obtener múltiples ads en una llamada
        # Usamos el endpoint /ads con filtro por IDs
        try:
            params = {
                'fields': 'id,name,creative{id,name,thumbnail_url,image_url,video_id,object_type}',
                'filtering': json.dumps([{'field': 'id', 'operator': 'IN', 'value': unique_ids}]),
                'limit': len(unique_ids) + 10,
            }
            if self.appsecret_proof:
                params['appsecret_proof'] = self.appsecret_proof

            ads = account.get_ads(params=params)
            for ad in ads:
                ad_id = ad.get('id')
                creative = ad.get('creative', {})
                if creative:
                    creative_map[ad_id] = {
                        'thumbnail_url': creative.get('thumbnail_url'),
                        'image_url': creative.get('image_url'),
                        'creative_type': creative.get('object_type') or 'image',
                        'creative_name': creative.get('name'),
                    }
        except Exception as e:
            _logger.warning('No se pudo obtener creative data: %s', e)

        return creative_map

    def _fetch_with_retry(self, account, fields, params, max_retries=5):
        """Ejecuta get_insights con backoff exponencial ante rate limits."""
        for attempt in range(1, max_retries + 1):
            try:
                return account.get_insights(fields=fields, params=params)
            except FacebookRequestError as e:
                code = e.api_error_code() if hasattr(e, 'api_error_code') else None
                subcode = e.api_error_subcode() if hasattr(e, 'api_error_subcode') else None
                msg = e.api_error_message() if hasattr(e, 'api_error_message') else str(e)

                # Rate limit
                is_rate_limit = (
                    code in (80000, 80001, 80002, 80003, 80004, 32, 4)
                    or 'rate limit' in msg.lower()
                    or 'too many calls' in msg.lower()
                )

                if is_rate_limit and attempt < max_retries:
                    sleep_seconds = min(2 ** attempt, 120)
                    _logger.warning(
                        'Meta API rate limit (intento %s/%s). Esperando %ss...',
                        attempt, max_retries, sleep_seconds,
                    )
                    time.sleep(sleep_seconds)
                    continue

                # Token expirado / permisos
                if code in (190, 102):
                    raise RuntimeError(
                        f"Token inválido o expirado. Revise las credenciales. Error: {msg}"
                    )
                if code == 10 or 'permission' in msg.lower():
                    raise RuntimeError(
                        f"Permisos insuficientes para acceder a la cuenta. Error: {msg}"
                    )

                raise RuntimeError(f"Meta API error {code}/{subcode}: {msg}")
            except Exception as e:
                if attempt < max_retries:
                    sleep_seconds = min(2 ** attempt, 60)
                    _logger.warning(
                        'Meta API error (intento %s/%s): %s. Reintentando en %ss...',
                        attempt, max_retries, e, sleep_seconds,
                    )
                    time.sleep(sleep_seconds)
                    continue
                raise
        return []

    def _normalize_insights(self, insights, level):
        """Convierte objetos Insights de Meta en lista de dicts planos."""
        records = []
        for insight in insights:
            row = {}
            # Campos base
            row['date'] = insight.get('date_start') or insight.get('date_start')
            row['campaign_id'] = insight.get('campaign_id', '')
            row['campaign_name'] = insight.get('campaign_name', '')
            row['adset_id'] = insight.get('adset_id', '')
            row['adset_name'] = insight.get('adset_name', '')
            row['ad_id'] = insight.get('ad_id', '')
            row['ad_name'] = insight.get('ad_name', '')

            # Métricas numéricas
            row['spend'] = self._to_float(insight.get('spend'))
            row['impressions'] = self._to_int(insight.get('impressions'))
            row['clicks'] = self._to_int(insight.get('clicks'))
            row['ctr'] = self._to_float(insight.get('ctr'))
            row['cpc'] = self._to_float(insight.get('cpc'))
            row['cpm'] = self._to_float(insight.get('cpm'))
            row['reach'] = self._to_int(insight.get('reach'))
            row['frequency'] = self._to_float(insight.get('frequency'))

            # Conversiones (se serializan como JSON string para BigQuery)
            row['purchase_roas'] = self._serialize_actions(insight.get('purchase_roas'))
            row['actions'] = self._serialize_actions(insight.get('actions'))
            row['action_values'] = self._serialize_actions(insight.get('action_values'))
            row['cost_per_action_type'] = self._serialize_actions(insight.get('cost_per_action_type'))

            # Clics de enlace y salientes
            row['inline_link_clicks'] = self._to_int(insight.get('inline_link_clicks'))
            row['inline_link_click_ctr'] = self._to_float(insight.get('inline_link_click_ctr'))
            row['outbound_clicks'] = self._to_int(insight.get('outbound_clicks'))

            # Video (listas tipo actions, se serializan como JSON)
            row['video_play_actions'] = self._serialize_actions(insight.get('video_play_actions'))
            row['video_p25_watched_actions'] = self._serialize_actions(insight.get('video_p25_watched_actions'))
            row['video_p50_watched_actions'] = self._serialize_actions(insight.get('video_p50_watched_actions'))
            row['video_p75_watched_actions'] = self._serialize_actions(insight.get('video_p75_watched_actions'))
            row['video_p100_watched_actions'] = self._serialize_actions(insight.get('video_p100_watched_actions'))

            # Rankings de calidad (solo nivel anuncio)
            if level == 'ad':
                row['quality_ranking'] = insight.get('quality_ranking') or ''
                row['engagement_rate_ranking'] = insight.get('engagement_rate_ranking') or ''
                row['conversion_rate_ranking'] = insight.get('conversion_rate_ranking') or ''

            # Filtrar campos vacíos según nivel para mantener schema limpio
            if level == 'campaign':
                row.pop('adset_id', None)
                row.pop('adset_name', None)
                row.pop('ad_id', None)
                row.pop('ad_name', None)
            elif level == 'adset':
                row.pop('ad_id', None)
                row.pop('ad_name', None)

            records.append(row)
        return records

    @staticmethod
    def _to_float(val):
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _to_int(val):
        if val is None:
            return 0
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _serialize_actions(actions):
        """Serializa lista de acciones a string JSON para BigQuery."""
        if not actions:
            return None
        if isinstance(actions, list):
            return json.dumps(actions)
        if isinstance(actions, dict):
            return json.dumps(actions)
        return str(actions)
