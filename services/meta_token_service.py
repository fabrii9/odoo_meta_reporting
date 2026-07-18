# -*- coding: utf-8 -*-
"""Servicio para gestionar tokens de acceso de Meta (larga duración y renovación)."""
import logging
import requests

_logger = logging.getLogger(__name__)


class MetaTokenService:
    """Maneja intercambio, validación y renovación de tokens de Meta."""

    GRAPH_API_URL = 'https://graph.facebook.com/v19.0'

    def __init__(self, app_id, app_secret):
        self.app_id = (app_id or '').strip()
        self.app_secret = (app_secret or '').strip()

    def get_long_lived_token(self, short_lived_token):
        """
        Intercambia un token de corta duración (~2 horas) por uno de larga duración (~60 días).
        Documentación: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived
        """
        url = f'{self.GRAPH_API_URL}/oauth/access_token'
        params = {
            'grant_type': 'fb_exchange_token',
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'fb_exchange_token': short_lived_token,
        }
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return {
                'access_token': data.get('access_token'),
                'token_type': data.get('token_type'),
                'expires_in': data.get('expires_in'),  # segundos
            }
        except requests.exceptions.HTTPError as e:
            error_body = e.response.json() if e.response.content else {}
            error_msg = error_body.get('error', {}).get('message', str(e))
            _logger.error('Meta Token error HTTP %s: %s', e.response.status_code, error_msg)
            raise RuntimeError(f'Error obteniendo token de larga duración: {error_msg}')
        except Exception as e:
            _logger.error('Meta Token error: %s', e)
            raise RuntimeError(f'Error obteniendo token de larga duración: {e}')

    def debug_token(self, access_token):
        """
        Consulta información de un token (tipo, expiración, scopes).
        Retorna dict con expires_at, scopes, is_valid, etc.
        """
        url = f'{self.GRAPH_API_URL}/debug_token'
        params = {
            'input_token': access_token,
            'access_token': f'{self.app_id}|{self.app_secret}',
        }
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('data', {})
        except Exception as e:
            _logger.error('Meta debug_token error: %s', e)
            raise RuntimeError(f'Error consultando token: {e}')

    def get_token_expiration(self, access_token):
        """Retorna (is_valid, expires_at_timestamp, seconds_to_expire)."""
        try:
            info = self.debug_token(access_token)
            is_valid = info.get('is_valid', False)
            expires_at = info.get('expires_at')
            if expires_at and expires_at > 0:
                import time
                seconds_to_expire = expires_at - int(time.time())
                return is_valid, expires_at, seconds_to_expire
            return is_valid, expires_at, None
        except Exception:
            return False, None, None

    def refresh_token(self, current_token):
        """
        Renueva un token de larga duración existente.
        Meta permite renovar tokens de larga duración si aún no expiraron
        y si se usaron recientemente. Se usa el mismo endpoint de exchange.
        """
        # Para renovar, simplemente hacemos el mismo exchange
        return self.get_long_lived_token(current_token)
