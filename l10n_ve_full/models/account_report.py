# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de account.report para Reportes Financieros Bimoneda
=============================================================================
Usa el sistema nativo de options['buttons'] de Odoo Enterprise account_reports
para agregar el botón [💵 Moneda: Bs.F / $] en la barra de reportes financieros.

Compatible con: Odoo Enterprise 19.0 (account_reports module)
Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountReport(models.Model):
    _inherit = 'account.report'

    # Campo NO almacenado en DB (store=False) para evitar errores de columna SQL
    filter_l10n_ve_currency = fields.Boolean(
        string="Bimoneda Dual (Bs.F / $)",
        default=True,
        store=False,
        compute='_compute_filter_l10n_ve_currency',
    )

    def _compute_filter_l10n_ve_currency(self):
        for report in self:
            report.filter_l10n_ve_currency = True

    # ─── Override del método principal de opciones de Enterprise ─────────────
    def get_options(self, previous_options=None):
        options = super().get_options(previous_options)

        # Leer la moneda seleccionada del request anterior (persistencia de sesión)
        selected_currency = 'bs'
        if previous_options and isinstance(previous_options, dict):
            selected_currency = previous_options.get('l10n_ve_currency', 'bs')

        # Inyectar opciones bimoneda en el diccionario de opciones del reporte
        options['filter_l10n_ve_currency'] = True
        options['l10n_ve_currency'] = selected_currency
        options['l10n_ve_currency_label'] = '$' if selected_currency == 'usd' else 'Bs.F'
        options['l10n_ve_badge_label'] = 'En .$' if selected_currency == 'usd' else 'En .Bs.F'

        # ── Agregar botón nativo a la barra de herramientas del reporte ───────
        # El sistema de Enterprise renderiza la lista options['buttons'] como
        # botones de acción en la barra superior del reporte financiero.
        buttons = options.get('buttons', [])

        # Remover botones previos de moneda para evitar duplicados
        buttons = [b for b in buttons if isinstance(b, dict) and b.get('action') != 'action_switch_l10n_ve_currency']

        # Etiqueta del botón con ícono y moneda activa
        btn_label = f"💵 Moneda: {options['l10n_ve_currency_label']}"

        # Insertar al principio (secuencia 1 para que aparezca antes de PDF/XLSX)
        buttons.insert(0, {
            'name': btn_label,
            'action': 'action_switch_l10n_ve_currency',
            'sequence': 1,
        })

        options['buttons'] = buttons
        return options

    # ─── Acción de cambio de moneda (llamada desde el clic del botón) ─────────
    def action_switch_l10n_ve_currency(self, options):
        """Toggle entre Bs.F y $ en el reporte financiero activo."""
        self.ensure_one()
        current = options.get('l10n_ve_currency', 'bs')
        new_currency = 'usd' if current == 'bs' else 'bs'

        # Retornar las nuevas opciones para que el frontend recargue el reporte
        return {
            'type': 'ir.actions.client',
            'tag': 'account_report',
            'options': {
                **options,
                'l10n_ve_currency': new_currency,
            },
        }

    # ─── Override del formateador de valores monetarios ──────────────────────
    def _format_value(self, options, value, figure_type, blank_if_zero=False, currency=None):
        try:
            if (options and isinstance(options, dict)
                    and figure_type == 'monetary'
                    and isinstance(value, (int, float))):

                ve_currency = options.get('l10n_ve_currency', 'bs')
                date_to = (options.get('date') or {}).get('date_to') or fields.Date.context_today(self)

                if ve_currency == 'usd':
                    rate_bcv = self._get_bcv_rate_for_date(date_to)
                    val_usd = round(value / rate_bcv, 2) if rate_bcv else value
                    fmt = f"{val_usd:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                    return f"$ {fmt}"

                elif ve_currency == 'bs':
                    fmt = f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                    return f"{fmt} Bs.F"

        except Exception as e:
            _logger.warning(f"[Venezuela360] _format_value error: {e}")

        return super()._format_value(options, value, figure_type, blank_if_zero=blank_if_zero, currency=currency)

    # ─── Helper: obtener tasa BCV oficial para una fecha ─────────────────────
    def _get_bcv_rate_for_date(self, date_to):
        rate_bcv = 777.4161  # fallback BCV actual
        try:
            company = self.env.company
            bs_curr = getattr(company, 'l10n_ve_currency_bs_id', None)
            if bs_curr:
                rate_rec = self.env['res.currency.rate'].search([
                    ('currency_id', '=', bs_curr.id),
                    ('name', '<=', date_to),
                ], order='name desc', limit=1)
                if rate_rec and rate_rec.rate > 0:
                    rate_bcv = rate_rec.rate if rate_rec.rate > 1.0 else (1.0 / rate_rec.rate)
        except Exception as e:
            _logger.warning(f"[Venezuela360] _get_bcv_rate_for_date error: {e}")
        return rate_bcv
