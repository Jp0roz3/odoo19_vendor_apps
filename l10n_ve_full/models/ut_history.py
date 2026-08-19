# -*- coding: utf-8 -*-
"""
Venezuela360: Unidad Tributaria Histórica
==========================================
Modelo: account.ut.history

Almacena el historial de valores de la Unidad Tributaria (UT) publicados
por el SENIAT. Permite calcular retenciones, límites de ISLR y otros
parámetros fiscales venezolanos usando el valor vigente en la fecha
del documento.

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountUtHistory(models.Model):
    """
    Histórico de Unidad Tributaria (UT) venezolana.

    Cada registro guarda el valor en Bs de la UT y la fecha de vigencia.
    Para obtener el valor en una fecha dada, se busca el registro más
    reciente con date_from <= fecha_consulta.
    """
    _name = 'account.ut.history'
    _description = 'Histórico de Unidad Tributaria (UT) — SENIAT Venezuela'
    _order = 'date_from desc, id desc'
    _rec_name = 'display_name'

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Denominación',
        required=True,
        help='Ej: "UT 2024 — Bs 9.000,00 (Providencia SNAT/2024/00XXX)"',
    )
    date_from = fields.Date(
        string='Vigente desde',
        required=True,
        index=True,
        default=fields.Date.context_today,
        help='Fecha a partir de la cual este valor de UT es vigente según Gaceta Oficial.',
    )
    date_to = fields.Date(
        string='Vigente hasta',
        help='Fecha de fin de vigencia. Vacío = vigente indefinidamente hasta nueva publicación.',
    )
    value_bs = fields.Float(
        string='Valor UT (Bs)',
        required=True,
        digits=(18, 2),
        help='Valor de la Unidad Tributaria en Bolívares según Gaceta Oficial.',
    )
    value_usd = fields.Float(
        string='Valor UT (USD)',
        digits=(12, 4),
        compute='_compute_value_usd',
        store=True,
        help='Equivalente en USD usando la tasa BCV vigente en la fecha de publicación.',
    )
    currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Bs',
        default=lambda self: self.env['res.currency'].search(
            [('name', 'in', ['VES', 'VEF', 'VEB'])], limit=1
        ),
    )
    exchange_rate_id = fields.Many2one(
        comodel_name='l10n_ve.exchange.rate',
        string='Tasa BCV Usada',
        help='Tasa BCV aplicada para calcular el equivalente en USD.',
    )
    gaceta_oficial = fields.Char(
        string='Gaceta Oficial N°',
        help='Número de Gaceta Oficial donde se publicó la UT (ej: 42.777).',
    )
    providencia = fields.Char(
        string='Providencia SNAT',
        help='Código de la Providencia Administrativa del SENIAT (ej: SNAT/2024/00012).',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    notes = fields.Text(string='Observaciones')
    active = fields.Boolean(default=True)

    # Campo calculado para nombre visible
    display_name = fields.Char(
        string='UT',
        compute='_compute_display_name_field',
        store=True,
    )

    # ------------------------------------------------------------------
    # SQL Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'unique_date_from_company',
            'UNIQUE(date_from, company_id)',
            'Ya existe un valor de UT para esta fecha de vigencia y compañía.',
        ),
        (
            'positive_value',
            'CHECK(value_bs > 0)',
            'El valor de la Unidad Tributaria debe ser mayor que cero.',
        ),
    ]

    # ------------------------------------------------------------------
    # Constraints Python
    # ------------------------------------------------------------------
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise ValidationError(
                    _('La fecha de fin de vigencia (%s) no puede ser anterior a la fecha de inicio (%s).')
                    % (rec.date_to, rec.date_from)
                )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('value_bs', 'exchange_rate_id', 'exchange_rate_id.rate')
    def _compute_value_usd(self):
        for rec in self:
            if rec.exchange_rate_id and rec.exchange_rate_id.rate:
                rec.value_usd = round(rec.value_bs / rec.exchange_rate_id.rate, 4)
            else:
                rec.value_usd = 0.0

    @api.depends('date_from', 'value_bs')
    def _compute_display_name_field(self):
        for rec in self:
            date_str = str(rec.date_from) if rec.date_from else '?'
            rec.display_name = f'UT {date_str} | Bs {rec.value_bs:,.2f}'

    # ------------------------------------------------------------------
    # Métodos de negocio
    # ------------------------------------------------------------------
    @api.model
    def get_ut_for_date(self, date, company_id=None):
        """
        Retorna el registro de UT vigente para la fecha dada.

        Parámetros:
            date       : datetime.date o string 'YYYY-MM-DD'
            company_id : int (ID de compañía). Si None, usa la activa.
        Retorna:
            account.ut.history (record) o None.
        """
        company_id = company_id or self.env.company.id
        ut = self.search([
            ('date_from', '<=', date),
            ('company_id', '=', company_id),
            ('active', '=', True),
        ], order='date_from desc', limit=1)

        if not ut:
            _logger.warning(
                'account.ut.history: Sin UT registrada para fecha %s, compañía %s.',
                date, company_id
            )
        return ut or None

    @api.model
    def get_ut_value_for_date(self, date, company_id=None):
        """
        Retorna directamente el valor float en Bs de la UT para una fecha.
        Retorna 0.0 si no hay UT registrada.
        """
        ut = self.get_ut_for_date(date, company_id)
        return ut.value_bs if ut else 0.0

    def compute_islr_units(self, amount_bs):
        """
        Calcula cuántas UT equivale un monto en Bs.
        Útil para el cálculo de ISLR basado en UT.
        """
        self.ensure_one()
        if not self.value_bs:
            return 0.0
        return round(amount_bs / self.value_bs, 4)

    def compute_amount_from_units(self, units):
        """
        Convierte un número de UT a Bs según el valor de este registro.
        """
        self.ensure_one()
        return round(units * self.value_bs, 2)
