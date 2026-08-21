# -*- coding: utf-8 -*-
"""
Venezuela360: Balance General Bimoneda ($ / Bs.F)
===================================================
Hereda account.report de Odoo Enterprise para agregar:

  1. Botón [💵 Moneda: Bs.F] / [💵 Moneda: $] en la barra del Balance General.
  2. Conversión automática de todos los valores monetarios según la moneda elegida.
  3. Tasa de cambio BCV leída en tiempo real desde l10n_ve.exchange.rate.

ARQUITECTURA:
─────────────────────────────────────────────────────────────────
  • Moneda PRINCIPAL: USD   (company.currency_id = USD)
  • Moneda SECUNDARIA: Bs.F (VES/VEF)
  • Los valores internos de Odoo están en USD (moneda base).
  • Modo 'bs'  → multiplica por tasa BCV → muestra en Bs.F
  • Modo 'usd' → muestra el valor tal cual en USD ($)

INTEGRACIÓN ENTERPRISE:
  • options['buttons'] → lista de botones nativos que Enterprise renderiza
    en la barra superior del reporte financiero.
  • action_switch_l10n_ve_currency(options) → retorna dict con las nuevas
    options (NO ir.actions.client); Enterprise recarga el reporte con ellas.
  • _format_value() → intercepta el formateador nativo y aplica conversión.
─────────────────────────────────────────────────────────────────

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# Fallback de tasa BCV si no hay registros en la BD (se actualiza al cargar)
_FALLBACK_RATE = 779.9522


class AccountReport(models.Model):
    _inherit = 'account.report'

    # ─────────────────────────────────────────────────────────────────────────
    # OPCIONES DEL REPORTE: inyección del selector bimoneda
    # ─────────────────────────────────────────────────────────────────────────

    def get_options(self, previous_options=None):
        """
        Override de get_options para inyectar el botón bimoneda.

        Enterprise llama este método cada vez que recarga el reporte.
        'previous_options' contiene las opciones de la carga anterior,
        lo que nos permite persistir la moneda seleccionada entre recargas.
        """
        options = super().get_options(previous_options)

        # ── Leer moneda seleccionada (persiste entre recargas via previous_options)
        selected_currency = 'usd'   # Moneda principal = USD por defecto
        if previous_options and isinstance(previous_options, dict):
            prev_val = previous_options.get('l10n_ve_currency')
            if prev_val in ('usd', 'bs'):
                selected_currency = prev_val

        # ── Inyectar claves bimoneda en el diccionario de opciones
        options['l10n_ve_currency']       = selected_currency
        options['l10n_ve_currency_label'] = '$' if selected_currency == 'usd' else 'Bs.F'
        options['l10n_ve_badge_label']    = '$ USD' if selected_currency == 'usd' else 'Bs.F'
        options['filter_l10n_ve_currency'] = True

        # ── Agregar botón nativo a la barra del reporte ──────────────────────
        # Enterprise renderiza la lista options['buttons'] como botones de acción.
        # Cada item: {'name': str, 'action': 'method_name', 'sequence': int}
        # Al hacer clic, Enterprise llama:
        #   account.report.browse(id).method_name(options)  → retorna new_options
        buttons = list(options.get('buttons') or [])

        # Eliminar botón previo de moneda para evitar duplicados en recargas
        buttons = [
            b for b in buttons
            if not (isinstance(b, dict) and b.get('action') == 'action_switch_l10n_ve_currency')
        ]

        # Etiqueta del botón: muestra la moneda ACTIVA y al hacer clic cambia a la otra
        if selected_currency == 'usd':
            btn_label = '💵 Moneda: $ (cambiar a Bs.F)'
        else:
            btn_label = '💵 Moneda: Bs.F (cambiar a $)'

        # sequence=1 → aparece primero, antes de los botones de PDF/XLSX
        buttons.insert(0, {
            'name': btn_label,
            'action': 'action_switch_l10n_ve_currency',
            'sequence': 1,
        })

        options['buttons'] = buttons
        return options

    # ─────────────────────────────────────────────────────────────────────────
    # ACCIÓN DEL BOTÓN: toggle de moneda
    # ─────────────────────────────────────────────────────────────────────────

    def action_switch_l10n_ve_currency(self, options):
        """
        Toggle entre USD y Bs.F en el reporte activo.

        Enterprise llama este método cuando el usuario hace clic en el botón.
        IMPORTANTE: debe retornar un dict con las nuevas opciones (NO ir.actions.client).
        Enterprise detecta el retorno y recarga el reporte con las nuevas opciones.
        """
        self.ensure_one()

        current  = (options or {}).get('l10n_ve_currency', 'usd')
        new_curr = 'bs' if current == 'usd' else 'usd'

        new_options = dict(options or {})
        new_options['l10n_ve_currency']        = new_curr
        new_options['l10n_ve_currency_label']  = '$' if new_curr == 'usd' else 'Bs.F'
        new_options['l10n_ve_badge_label']     = '$ USD' if new_curr == 'usd' else 'Bs.F'
        new_options['filter_l10n_ve_currency'] = True

        _logger.info(
            '[Venezuela360] Balance General: moneda cambiada %s → %s',
            current, new_curr
        )
        return new_options

    # ─────────────────────────────────────────────────────────────────────────
    # FORMATEADOR DE VALORES: conversión USD ↔ Bs.F
    # ─────────────────────────────────────────────────────────────────────────

    def _format_value(self, options, value, figure_type, blank_if_zero=False, currency=None):
        """
        Override del formateador nativo de Enterprise.

        Los valores internos del Balance General están en USD (moneda base).
        Si el usuario eligió ver en Bs.F → multiplicamos por la tasa BCV.
        Si eligió USD → mostramos directamente en $.

        Nota: Solo intercedemos con figure_type == 'monetary'. El resto
        (porcentajes, enteros, etc.) lo maneja el super() sin cambios.
        """
        try:
            if (options
                    and isinstance(options, dict)
                    and figure_type == 'monetary'
                    and isinstance(value, (int, float))):

                ve_currency = options.get('l10n_ve_currency', 'usd')

                if ve_currency == 'usd':
                    # Valores internos ya están en USD → formatear con símbolo $
                    fmt = self._ve_format_number(value)
                    return f'$ {fmt}'

                elif ve_currency == 'bs':
                    # Convertir USD → Bs.F usando tasa BCV oficial
                    date_to = (options.get('date') or {}).get('date_to') \
                              or str(fields.Date.context_today(self))
                    rate    = self._get_bcv_rate(date_to)
                    val_bs  = round(value * rate, 2)
                    fmt     = self._ve_format_number(val_bs)
                    return f'{fmt} Bs.F'

        except Exception as e:
            _logger.warning('[Venezuela360] _format_value error: %s', e)

        # Fallback: comportamiento nativo de Enterprise
        try:
            return super()._format_value(
                options, value, figure_type,
                blank_if_zero=blank_if_zero, currency=currency
            )
        except TypeError:
            # Algunas versiones de Enterprise no tienen el parámetro 'currency'
            return super()._format_value(
                options, value, figure_type, blank_if_zero=blank_if_zero
            )

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS INTERNOS
    # ─────────────────────────────────────────────────────────────────────────

    def _ve_format_number(self, value):
        """
        Formatea un número con separadores venezolanos:
        Punto (.) para miles, coma (,) para decimales.
        Ejemplo: 1234567.89 → '1.234.567,89'
        """
        # Formato con separadores ingleses → invertir separadores
        formatted = f'{abs(value):,.2f}'                # '1,234,567.89'
        formatted = formatted.replace(',', 'X')         # '1X234X567.89'
        formatted = formatted.replace('.', ',')         # '1X234X567,89'
        formatted = formatted.replace('X', '.')         # '1.234.567,89'
        return f'-{formatted}' if value < 0 else formatted

    def _get_bcv_rate(self, date_to):
        """
        Obtiene la tasa BCV oficial (Bs/USD) para una fecha dada.
        Lee desde l10n_ve.exchange.rate (tabla propia de Venezuela360).

        Fallback en cascada:
          1. l10n_ve.exchange.rate para la fecha exacta o anterior
          2. res.currency.rate (moneda nativa Odoo) para VES/VEF
          3. Constante FALLBACK global (_FALLBACK_RATE)
        """
        try:
            # ── Fuente 1: tabla histórica Venezuela360 ────────────────────────
            rate_rec = self.env['l10n_ve.exchange.rate'].search([
                ('date', '<=', date_to),
                ('active', '=', True),
                ('company_id', '=', self.env.company.id),
            ], order='date desc', limit=1)

            if rate_rec and rate_rec.rate > 1:
                return rate_rec.rate

            # ── Fuente 2: res.currency.rate (motor nativo Odoo) ──────────────
            CurrencyModel = self.env['res.currency'].with_context(active_test=False)
            ves = (
                CurrencyModel.search([('name', '=', 'VES')], limit=1)
                or CurrencyModel.search([('name', '=', 'VEF')], limit=1)
            )
            if ves:
                odoo_rate_rec = self.env['res.currency.rate'].search([
                    ('currency_id', '=', ves.id),
                    ('name', '<=', date_to),
                    ('company_id', '=', self.env.company.id),
                ], order='name desc', limit=1)

                if odoo_rate_rec and odoo_rate_rec.rate > 0:
                    rate = odoo_rate_rec.rate
                    # Si la moneda base es USD, rate ya es Bs/USD directamente
                    # Si es < 1, entonces es la inversa (USD/Bs) y la invertimos
                    return rate if rate > 1 else (1.0 / rate)

        except Exception as e:
            _logger.warning('[Venezuela360] _get_bcv_rate error: %s', e)

        # ── Fuente 3: fallback constante ──────────────────────────────────────
        _logger.warning(
            '[Venezuela360] _get_bcv_rate: usando fallback %.4f Bs/USD', _FALLBACK_RATE
        )
        return _FALLBACK_RATE
