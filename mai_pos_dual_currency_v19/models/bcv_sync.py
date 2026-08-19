# -*- coding: utf-8 -*-
import requests
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# APIs de respaldo en orden de prioridad
BCV_APIS = [
    {
        'name': 'dolarapi.com (oficial)',
        'url': 'https://ve.dolarapi.com/v1/dolares/oficial',
        'rate_key': 'promedio',
    },
    {
        'name': 'exchangerate-api (fallback)',
        'url': 'https://open.er-api.com/v6/latest/USD',
        'rate_key': None,  # Procesamiento especial
    },
]


class PosConfigBCVSync(models.Model):
    _inherit = 'pos.config'

    @api.model
    def _cron_update_bcv_rate(self):
        """Fetches the BCV exchange rate and updates pos.configs that have dual currency enabled.
        Tries multiple API sources as fallback."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Odoo'
        }
        rate = None

        # --- Intentar cada API en orden ---
        for api_cfg in BCV_APIS:
            try:
                response = requests.get(api_cfg['url'], headers=headers, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    if api_cfg['rate_key']:
                        rate = float(data.get(api_cfg['rate_key'], 0))
                    else:
                        # Fallback: open.er-api → rates.VES
                        rates = data.get('rates', {})
                        ves = rates.get('VES') or rates.get('VEF')
                        if ves:
                            rate = float(ves)
                    if rate and rate > 0:
                        _logger.info(f"[BCV Sync] Tasa obtenida de {api_cfg['name']}: {rate}")
                        break
                else:
                    _logger.warning(f"[BCV Sync] {api_cfg['name']}: status {response.status_code}")
            except Exception as e:
                _logger.warning(f"[BCV Sync] {api_cfg['name']} falló: {e}")

        if not rate or rate <= 0:
            _logger.error("[BCV Sync] No se pudo obtener la tasa de ninguna fuente.")
            return

        # --- Actualizar la moneda secundaria en res.currency.rate ---
        configs = self.search([('show_dual_currency', '=', True)])
        currencies_updated = set()

        for config in configs:
            if not config.show_currency:
                continue
            currency = config.show_currency

            if currency.id in currencies_updated:
                continue  # Evitar actualizar la misma moneda dos veces

            today = fields.Date.context_today(self)
            # Buscar si ya existe un registro de tasa para hoy
            rate_record = self.env['res.currency.rate'].search([
                ('currency_id', '=', currency.id),
                ('name', '=', today),
                ('company_id', '=', self.env.company.id),
            ], limit=1)

            if rate_record:
                rate_record.sudo().write({'rate': 1.0 / rate})
                _logger.info(f"[BCV Sync] Tasa actualizada: {currency.name} = {rate} Bs (record id={rate_record.id})")
            else:
                self.env['res.currency.rate'].sudo().create({
                    'currency_id': currency.id,
                    'name': today,
                    'rate': 1.0 / rate,
                    'company_id': self.env.company.id,
                })
                _logger.info(f"[BCV Sync] Nuevo registro de tasa creado: {currency.name} = {rate} Bs")

            currencies_updated.add(currency.id)

        _logger.info(f"[BCV Sync] Monedas actualizadas: {len(currencies_updated)}")
