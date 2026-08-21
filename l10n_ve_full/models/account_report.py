# -*- coding: utf-8 -*-
"""
Venezuela360: Reportes Financieros Bimoneda ($ / Bs.F)
======================================================
Hereda account.report de Odoo Enterprise para agregar:

  1. Moneda Principal por defecto: Dólares ($ / USD).
  2. Moneda Secundaria: Bolívares (Bs.F) a Tasa Oficial BCV.
  3. Selector interactivo [💱 Moneda: $] / [💱 Moneda: Bs.F] en la barra de filtros.
  4. Conversión dinámica e instantánea de todos los valores monetarios según la tasa BCV del día.
  5. Soporte para TODOS los reportes financieros:
     - Balance General (Balance Sheet)
     - Estado de Resultados (Profit and Loss)
     - Estado de Flujo de Efectivo (Cash Flow)
     - Libro Mayor (General Ledger)
     - Balance de Comprobación (Trial Balance)

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
    # OPCIONES DEL REPORTE: Moneda principal USD por defecto
    # ─────────────────────────────────────────────────────────────────────────

    def get_options(self, previous_options=None):
        """
        Inyecta las opciones de moneda dual en el diccionario de opciones del reporte.
        Moneda principal por defecto: 'usd' ($).
        Solo cambia a 'bs' cuando el usuario lo selecciona explícitamente.
        """
        options = super().get_options(previous_options)

        selected_currency = 'usd'
        if previous_options and isinstance(previous_options, dict):
            prev_val = previous_options.get('l10n_ve_currency')
            if prev_val in ('usd', 'bs'):
                selected_currency = prev_val

        options['l10n_ve_currency'] = selected_currency
        options['l10n_ve_currency_label'] = '$' if selected_currency == 'usd' else 'Bs.F'
        options['l10n_ve_badge_label'] = 'En .$' if selected_currency == 'usd' else 'En .Bs.F'
        options['filter_l10n_ve_currency'] = True

        return options

    # ─────────────────────────────────────────────────────────────────────────
    # ACCIÓN NATIVA: Conmutar moneda
    # ─────────────────────────────────────────────────────────────────────────

    def action_switch_l10n_ve_currency(self, options):
        """
        Conmuta la moneda activa entre 'usd' y 'bs' y retorna la recarga del reporte.
        """
        self.ensure_one()
        current = (options or {}).get('l10n_ve_currency', 'usd')
        new_curr = 'bs' if current == 'usd' else 'usd'

        new_options = dict(options or {})
        new_options['l10n_ve_currency'] = new_curr
        new_options['l10n_ve_currency_label'] = '$' if new_curr == 'usd' else 'Bs.F'
        new_options['l10n_ve_badge_label'] = 'En .$' if new_curr == 'usd' else 'En .Bs.F'
        new_options['filter_l10n_ve_currency'] = True

        _logger.info(
            '[Venezuela360] Reporte %s: Moneda conmutada %s → %s',
            self.name, current, new_curr
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'account_report',
            'options': new_options,
            'ignore_session': 'both',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # GENERACIÓN Y CONVERSIÓN DE LÍNEAS DEL REPORTE
    # ─────────────────────────────────────────────────────────────────────────

    def _get_lines(self, options, *args, **kwargs):
        """
        Sobrescribe la generación de líneas de Odoo Enterprise para asegurar que
        cuando se seleccione 'bs', todas las columnas monetarias muestren los montos
        convertidos a tasa BCV en Bs.F, y en 'usd' muestren los dólares base.
        """
        lines = super()._get_lines(options, *args, **kwargs)
        try:
            ve_currency = (options or {}).get('l10n_ve_currency', 'usd')
            date_to = ((options or {}).get('date') or {}).get('date_to') or str(fields.Date.context_today(self))
            rate = self._get_bcv_rate(date_to)

            for line in lines:
                columns = line.get('columns', [])
                for col in columns:
                    if isinstance(col, dict):
                        raw_val = col.get('no_format')
                        if raw_val is not None and isinstance(raw_val, (int, float)):
                            figure_type = col.get('figure_type', 'monetary')
                            if figure_type in ('monetary', None):
                                if ve_currency == 'bs':
                                    val_bs = round(raw_val * rate, 2)
                                    col['name'] = f"{self._ve_format_number(val_bs)} Bs.F"
                                else:
                                    col['name'] = f"{self._ve_format_number(raw_val)} $"
        except Exception as e:
            _logger.warning('[Venezuela360] _get_lines formatting error: %s', e)

        return lines

    # ─────────────────────────────────────────────────────────────────────────
    # FORMATEADOR DE VALORES MONETARIOS (USD ↔ Bs.F)
    # ─────────────────────────────────────────────────────────────────────────

    def _format_value(self, options, value, figure_type='monetary', *args, **kwargs):
        """
        Intercepta el formateo de celdas monetarias para aplicar la conversión a tasa BCV.
        """
        try:
            if options and isinstance(options, dict) and isinstance(value, (int, float)):
                if figure_type in ('monetary', None):
                    ve_currency = options.get('l10n_ve_currency', 'usd')
                    if ve_currency == 'bs':
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

        return super()._format_value(options, value, figure_type, *args, **kwargs)

    def _format_monetary_value(self, options, value, *args, **kwargs):
        """
        Intercepta _format_monetary_value en Odoo Enterprise para soporte integral.
        """
        try:
            if options and isinstance(options, dict) and isinstance(value, (int, float)):
                ve_currency = options.get('l10n_ve_currency', 'usd')
                if ve_currency == 'bs':
                    date_to = (options.get('date') or {}).get('date_to') or str(fields.Date.context_today(self))
                    rate = self._get_bcv_rate(date_to)
                    val_bs = round(value * rate, 2)
                    fmt = self._ve_format_number(val_bs)
                    return f'{fmt} Bs.F'
                elif ve_currency == 'usd':
                    fmt = self._ve_format_number(value)
                    return f'{fmt} $'
        except Exception as e:
            _logger.warning('[Venezuela360] _format_monetary_value error: %s', e)

        if hasattr(super(), '_format_monetary_value'):
            return super()._format_monetary_value(options, value, *args, **kwargs)
        return self._format_value(options, value, figure_type='monetary', *args, **kwargs)

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
