# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class MetaAdsAccount(models.Model):
    _name = 'meta.ads.account'
    _description = 'Cuenta Publicitaria de Meta Ads'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Nombre', required=True, tracking=True)
    ad_account_id = fields.Char(
        string='Ad Account ID',
        required=True,
        help='Ejemplo: 123456789 o act_123456789',
        tracking=True,
    )
    business_id = fields.Char(
        string='Business ID',
        help='ID de Business Manager',
        tracking=True,
    )
    access_token = fields.Char(
        string='Access Token',
        required=True,
        password=True,
        help='Token de acceso a la Meta Marketing API',
        tracking=True,
    )
    app_id = fields.Char(
        string='App ID',
        required=True,
        help='App ID de Meta for Developers',
        tracking=True,
    )
    app_secret = fields.Char(
        string='App Secret',
        required=True,
        password=True,
        help='App Secret de Meta for Developers',
        tracking=True,
    )
    is_active = fields.Boolean(string='Activa', default=True, tracking=True)
    token_expires_at = fields.Datetime(
        string='Expiración del Token',
        readonly=True,
        help='Fecha y hora de expiración del token actual',
    )
    token_status = fields.Selection(
        [
            ('unknown', 'Desconocido'),
            ('valid', 'Válido'),
            ('expiring', 'Por expirar'),
            ('expired', 'Expirado'),
        ],
        string='Estado del Token',
        default='unknown',
        readonly=True,
        tracking=True,
    )
    last_sync = fields.Datetime(string='Última Sincronización', readonly=True)
    sync_status = fields.Selection(
        [
            ('idle', 'Inactiva'),
            ('running', 'Sincronizando...'),
            ('error', 'Error'),
            ('success', 'Éxito'),
        ],
        string='Estado de Sync',
        default='idle',
        readonly=True,
        tracking=True,
    )
    dataset_id = fields.Many2one(
        'meta.ads.dataset',
        string='Dataset BigQuery',
        required=True,
        help='Configuración de BigQuery donde se cargarán los datos',
        tracking=True,
    )
    sync_level = fields.Selection(
        [
            ('campaign', 'Campaña'),
            ('adset', 'Adset'),
            ('ad', 'Anuncio'),
        ],
        string='Nivel de Extracción',
        default='campaign',
        required=True,
        help='Granularidad de los datos a extraer',
        tracking=True,
    )
    sync_all_levels = fields.Boolean(
        string='Sincronizar todos los niveles',
        default=True,
        help='Si está activado, sincroniza campaña, adset y anuncio. '
             'Si está desactivado, usa solo el nivel seleccionado.',
        tracking=True,
    )
    log_ids = fields.One2many(
        'meta.ads.sync.log',
        'account_id',
        string='Logs de Sincronización',
        readonly=True,
    )

    @api.constrains('ad_account_id')
    def _check_ad_account_id(self):
        for rec in self:
            raw = (rec.ad_account_id or '').strip().lower()
            if raw.startswith('act_'):
                raw = raw[4:]
            if not raw.isdigit():
                raise UserError(_('El Ad Account ID debe ser numérico (ej: 123456789 o act_123456789).'))

    def _get_clean_account_id(self):
        self.ensure_one()
        raw = (self.ad_account_id or '').strip().lower()
        if raw.startswith('act_'):
            return raw[4:]
        return raw

    def action_test_connection_meta(self):
        self.ensure_one()
        try:
            from ..services.meta_api_service import MetaApiService
            service = MetaApiService(
                app_id=self.app_id,
                app_secret=self.app_secret,
                access_token=self.access_token,
            )
            service.test_connection(self._get_clean_account_id())
            self._check_token_expiration()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Conexión con Meta API exitosa.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as e:
            _logger.exception('Error testeando conexión Meta')
            raise UserError(_('Error de conexión con Meta: %s') % str(e))

    def action_generate_long_lived_token(self):
        """Genera un token de larga duración a partir del token actual."""
        self.ensure_one()
        try:
            from ..services.meta_token_service import MetaTokenService
            service = MetaTokenService(
                app_id=self.app_id,
                app_secret=self.app_secret,
            )
            result = service.get_long_lived_token(self.access_token)
            self.access_token = result['access_token']
            self._check_token_expiration()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Token de larga duración generado y guardado.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as e:
            _logger.exception('Error generando token de larga duración')
            raise UserError(_('Error generando token: %s') % str(e))

    def action_refresh_token(self):
        """Renueva el token actual si es de larga duración."""
        self.ensure_one()
        try:
            from ..services.meta_token_service import MetaTokenService
            service = MetaTokenService(
                app_id=self.app_id,
                app_secret=self.app_secret,
            )
            result = service.refresh_token(self.access_token)
            self.access_token = result['access_token']
            self._check_token_expiration()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Token renovado exitosamente.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as e:
            _logger.exception('Error renovando token')
            raise UserError(_('Error renovando token: %s') % str(e))

    @api.model
    def cron_refresh_expiring_tokens(self):
        """Cron semanal: renueva tokens que estén por expirar (menos de 7 días)."""
        accounts = self.sudo().search([
            ('is_active', '=', True),
            ('access_token', '!=', False),
        ])
        for account in accounts:
            try:
                account._check_token_expiration()
                if account.token_status == 'expiring':
                    account.action_refresh_token()
                    _logger.info('Token renovado automáticamente para cuenta %s', account.name)
            except Exception as e:
                _logger.warning('Error renovando token para cuenta %s: %s', account.name, e)
        return True

    def _check_token_expiration(self):
        """Actualiza los campos de expiración del token."""
        self.ensure_one()
        try:
            from ..services.meta_token_service import MetaTokenService
            service = MetaTokenService(
                app_id=self.app_id,
                app_secret=self.app_secret,
            )
            is_valid, expires_at, seconds_to_expire = service.get_token_expiration(self.access_token)
            if not is_valid:
                self.token_status = 'expired'
                self.token_expires_at = False
                return
            if expires_at:
                from datetime import datetime
                self.token_expires_at = datetime.fromtimestamp(expires_at)
                if seconds_to_expire and seconds_to_expire < 7 * 24 * 3600:  # 7 días
                    self.token_status = 'expiring'
                else:
                    self.token_status = 'valid'
            else:
                # Token sin expiración (system user o app token)
                self.token_expires_at = False
                self.token_status = 'valid'
        except Exception as e:
            _logger.warning('No se pudo verificar expiración del token: %s', e)
            self.token_status = 'unknown'

    def action_sync_now(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sincronizar Ahora'),
            'res_model': 'meta.ads.sync.manual.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_account_id': self.id,
            },
        }

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Logs de Sincronización'),
            'res_model': 'meta.ads.sync.log',
            'view_mode': 'tree,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }
