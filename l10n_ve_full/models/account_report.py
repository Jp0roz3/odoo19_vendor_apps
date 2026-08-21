# -*- coding: utf-8 -*-
"""
Venezuela360: Reportes Financieros Bimoneda ($ / Bs.F)
======================================================
Hereda account.report de Odoo Enterprise para agregar:

  1. Selector interactivo [💱 Moneda: Bs.F] / [💱 Moneda: $] en la barra de filtros.
  2. Conversión dinámica de todos los valores monetarios según la tasa BCV a la fecha del reporte.
  3. Soporte para TODOS los reportes financieros:
     - Balance General (Balance Sheet)
     - Estado de Resultados (Profit and Loss)
     - Estado de Flujo de Efectivo (Cash Flow)
     - Libro Mayor (General Ledger)
     - Balance de Comprobación (Trial Balance)
     - Resumen Ejecutivo y demás reportes de account.report.

ARQUITECTURA:
─────────────────────────────────────────────────────────────────
  • Moneda PRINCIPAL de la empresa: USD (company.currency_id = USD)
  • Moneda SECUNDARIA: Bs.F (VES / VEF)
  • Los importes internos de Odoo se calculan en USD (moneda base).
  • Modo 'bs'  → Multiplica por tasa BCV de la fecha de corte → Formatea como 'X.XXX,XX Bs.F'
  • Modo 'usd' → Muestra los valores directamente en USD ($)
─────────────────────────────────────────────────────────────────

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# Fallback de tasa BCV por defecto si no existen registros previos
_FALLBACK_RATE = 779.9522


class AccountReport(models.Model):
    _inherit = 'account.report'

    # ─────────────────────────────────────────────────────────────────────────
    # OPCIONES DEL REPORTE: Inyección del selector bimoneda
    # ─────────────────────────────────────────────────────────────────────────

    def get_options(self, previous_options=None):
        """
        Inyecta las opciones de moneda dual en el diccionario de opciones del reporte.
        Persiste la selección del usuario (USD o Bs.F) entre recargas.
        """
        options = super().get_options(previous_options)

        # Determinar moneda activa (por defecto 'bs' para visualización venezolana en Bs.F o 'usd')
        selected_currency = 'bs'
        if previous_options and isinstance(previous_options, dict):
            prev_val = previous_options.get('l10n_ve_currency')
            if prev_val in ('usd', 'bs'):
                selected_currency = prev_val

        # Claves de opciones para control en Python y en OWL
        options['l10n_ve_currency'] = selected_currency
        options['l10n_ve_currency_label'] = 'Bs.F' if selected_currency == 'bs' else '$'
        options['l10n_ve_badge_label'] = 'En .Bs.F' if selected_currency == 'bs' else 'En $'
        options['filter_l10n_ve_currency'] = True

        # Botón nativo de respaldo en options['buttons'] (aparece en la barra de acciones)
        buttons = list(options.get('buttons') or [])
        buttons = [
            b for b in buttons
            if not (isinstance(b, dict) and b.get('action') == 'action_switch_l10n_ve_currency')
        ]

        if selected_currency == 'bs':
            btn_label = '💱 Moneda: Bs.F (Ver en $)'
        else:
            btn_label = '💱 Moneda: $ (Ver en Bs.F)'

        buttons.insert(0, {
            'name': btn_label,
            'action': 'action_switch_l10n_ve_currency',
            'sequence': 1,
        })
        options['buttons'] = buttons

        return options

    # ─────────────────────────────────────────────────────────────────────────
    # ACCIÓN NATIVA: Conmutar moneda
    # ─────────────────────────────────────────────────────────────────────────

    def action_switch_l10n_ve_currency(self, options):
        """
        Conmuta la moneda activa entre 'usd' y 'bs' y retorna el diccionario
        de opciones actualizado para recargar el reporte en Enterprise.
        """
        self.ensure_one()
        current = (options or {}).get('l10n_ve_currency', 'bs')
        new_curr = 'usd' if current == 'bs' else 'bs'

        new_options = dict(options or {})
        new_options['l10n_ve_currency'] = new_curr
        new_options['l10n_ve_currency_label'] = 'Bs.F' if new_curr == 'bs' else '$'
        new_options['l10n_ve_badge_label'] = 'En .Bs.F' if new_curr == 'bs' else 'En $'
        new_options['filter_l10n_ve_currency'] = True

        _logger.info(
            '[Venezuela360] Reporte %s: Moneda conmutada %s → %s',
            self.name, current, new_curr
        )
        return new_options

    # ─────────────────────────────────────────────────────────────────────────
    # FORMATEADOR DE VALORES MONETARIOS (USD ↔ Bs.F)
    # ─────────────────────────────────────────────────────────────────────────

    def _format_value(self, options, value, figure_type, *args, **kwargs):
        """
        Intercepta el formateo monetario de celdas para aplicar la conversión a tasa BCV.
        Firma compatible con todas las versiones y variantes de Odoo 19 (*args, **kwargs).
        """
        try:
            if (options
                    and isinstance(options, dict)
                    and figure_type == 'monetary'
                    and isinstance(value, (int, float))):

                ve_currency = options.get('l10n_ve_currency', 'bs')

                if ve_currency == 'bs':
                    # Obtener fecha de corte del reporte
                    date_to = (options.get('date') or {}).get('date_to') or str(fields.Date.context_today(self))
                    rate = self._get_bcv_rate(date_to)
                    val_bs = round(value * rate, 2)
                    fmt = self._ve_format_number(val_bs)
                    return f'{fmt} Bs.F'

                elif ve_currency == 'usd':
                    fmt = self._ve_format_number(value)
                    return f'{fmt} $'

        except Exception as e:
            _logger.warning('[Venezuela360] _format_value error: %s', e)

        # Fallback al comportamiento nativo de Odoo
        return super()._format_value(options, value, figure_type, *args, **kwargs)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS Y CONSULTA DE TASA BCV
    # ─────────────────────────────────────────────────────────────────────────

    def _ve_format_number(self, value):
        """
        Formatea números con estándar venezolano:
        Separador de miles: punto (.)
        Separador de decimales: coma (,)
        Ejemplo: 29284126.27 → '29.284.126,27'
                 -93664550.95 → '-93.664.550,95'
        """
        formatted = f'{abs(value):,.2f}'
        formatted = formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f'-{formatted}' if value < 0 else formatted

    def _get_bcv_rate(self, date_to):
        """
        Obtiene la tasa oficial BCV (Bs/USD) para la fecha de corte del reporte.
        Búsqueda jerárquica:
          1. l10n_ve.exchange.rate para fecha <= date_to y compañía activa.
          2. res.currency.rate nativo para VES.
          3. Tasa actual de la compañía.
          4. Fallback seguro _FALLBACK_RATE.
        """
        try:
            company_id = self.env.company.id

            # Fuente 1: Histórico l10n_ve.exchange.rate
            rate_rec = self.env['l10n_ve.exchange.rate'].search([
                ('date', '<=', date_to),
                ('active', '=', True),
                ('company_id', '=', company_id),
            ], order='date desc, id desc', limit=1)

            if rate_rec and rate_rec.rate > 0:
                return rate_rec.rate

            # Fuente 2: res.currency.rate
            CurrencyModel = self.env['res.currency'].with_context(active_test=False)
            ves = (
                CurrencyModel.search([('name', '=', 'VES')], limit=1)
                or CurrencyModel.search([('name', '=', 'VEF')], limit=1)
            )
            if ves:
                odoo_rate_rec = self.env['res.currency.rate'].search([
                    ('currency_id', '=', ves.id),
                    ('name', '<=', date_to),
                    ('company_id', 'in', [company_id, False]),
                ], order='name desc, id desc', limit=1)

                if odoo_rate_rec and odoo_rate_rec.rate > 0:
                    rate = odoo_rate_rec.rate
                    return rate if rate > 1.0 else (1.0 / rate)

            # Fuente 3: Tasa de compañía
            if hasattr(self.env.company, 'get_current_bcv_rate'):
                comp_rate = self.env.company.get_current_bcv_rate()
                if comp_rate and comp_rate > 0:
                    return comp_rate

        except Exception as e:
            _logger.warning('[Venezuela360] _get_bcv_rate error: %s', e)

        return _FALLBACK_RATE
