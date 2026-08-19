# -*- coding: utf-8 -*-
"""
Venezuela360: Retención ISLR (account.wh.islr)
================================================
Retención de Impuesto Sobre la Renta según el Decreto con Rango, Valor
y Fuerza de Ley de Impuesto Sobre la Renta (ISLR) de Venezuela.

Soporta:
- Conceptos SENIAT configurables (tabla de conceptos)
- Cálculo por método de sustraendo o porcentaje directo
- Cálculo basado en Unidades Tributarias (UT)
- Comprobante PDF numerado
- Asiento contable automático
- Doble moneda BS/USD

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountWhIslrConcept(models.Model):
    """
    Catálogo de conceptos de retención ISLR del SENIAT.
    Cada concepto tiene una tasa y un sustraendo configurables.
    """
    _name = 'account.wh.islr.concept'
    _description = 'Concepto de Retención ISLR — SENIAT'
    _order = 'code, name'

    code = fields.Char(
        string='Código SENIAT',
        required=True,
        size=10,
        help='Código oficial del concepto en el formulario del SENIAT (ej: 01, 02, 09).',
    )
    name = fields.Char(
        string='Descripción del Concepto',
        required=True,
        help='Descripción oficial del concepto de retención.',
    )
    wh_rate = fields.Float(
        string='Tasa de Retención (%)',
        required=True,
        digits=(5, 4),
        help='Porcentaje de retención sobre el monto pagado (ej: 3.0000% para honorarios).',
    )
    subtract = fields.Float(
        string='Sustraendo (Bs)',
        digits=(18, 2),
        default=0.0,
        help=(
            'Monto fijo en Bs que se resta al monto calculado por porcentaje. '
            'Usado en el método de sustraendo para el cálculo de ISLR tabular.'
        ),
    )
    calculation_method = fields.Selection([
        ('percentage', 'Porcentaje Directo sobre Monto Pagado'),
        ('subtract',   'Método de Sustraendo (% - Sustraendo)'),
        ('ut_table',   'Tabla en Unidades Tributarias (UT)'),
    ], string='Método de Cálculo',
       required=True,
       default='percentage',
       help='Método oficial del SENIAT para calcular el ISLR para este concepto.',
    )
    applicable_to = fields.Selection([
        ('natural',   'Persona Natural'),
        ('juridica',  'Persona Jurídica'),
        ('both',      'Ambas'),
    ], string='Aplica a', default='both',
    )
    notes = fields.Text(string='Observaciones Legales')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'El código de concepto ISLR debe ser único.'),
    ]


class AccountWhIslr(models.Model):
    """Comprobante de Retención de ISLR."""
    _name = 'account.wh.islr'
    _description = 'Retención de ISLR — Venezuela'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    # ------------------------------------------------------------------
    # Campos principales
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Número de Comprobante ISLR',
        required=True,
        copy=False,
        default='/',
        tracking=True,
    )
    state = fields.Selection([
        ('draft',     'Borrador'),
        ('confirmed', 'Confirmado'),
        ('posted',    'Contabilizado'),
        ('cancel',    'Cancelado'),
    ], string='Estado', default='draft', required=True, copy=False, tracking=True,
    )

    # ------------------------------------------------------------------
    # Relación con factura
    # ------------------------------------------------------------------
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura Origen',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        related='move_id.partner_id',
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='move_id.company_id',
        store=True,
    )

    # ------------------------------------------------------------------
    # Concepto ISLR
    # ------------------------------------------------------------------
    concept_id = fields.Many2one(
        comodel_name='account.wh.islr.concept',
        string='Concepto ISLR',
        required=True,
        help='Concepto de retención según la tabla del SENIAT.',
    )
    calculation_method = fields.Selection(
        related='concept_id.calculation_method',
        string='Método de Cálculo',
        store=True,
    )

    # ------------------------------------------------------------------
    # Fechas
    # ------------------------------------------------------------------
    date = fields.Date(
        string='Fecha de Retención',
        required=True,
        default=fields.Date.context_today,
        copy=False,
        tracking=True,
    )

    # ------------------------------------------------------------------
    # Tasa BCV y UT
    # ------------------------------------------------------------------
    rate = fields.Float(
        string='Tasa Bs/USD',
        related='move_id.l10n_ve_rate',
        store=True,
        digits=(18, 6),
    )
    ut_id = fields.Many2one(
        comodel_name='account.ut.history',
        string='UT Vigente',
        related='move_id.l10n_ve_ut_id',
        store=True,
    )
    ut_value = fields.Float(
        string='Valor UT (Bs)',
        related='move_id.l10n_ve_ut_value',
        store=True,
        digits=(18, 2),
    )

    # ------------------------------------------------------------------
    # Base de cálculo
    # ------------------------------------------------------------------
    taxable_amount_bs = fields.Monetary(
        string='Monto Gravable (Bs)',
        currency_field='currency_bs_id',
        required=True,
        compute='_compute_taxable_amount',
        store=True,
        help='Base de cálculo de la retención ISLR en Bolívares.',
    )
    taxable_amount_usd = fields.Float(
        string='Monto Gravable (USD)',
        digits=(18, 4),
        compute='_compute_taxable_amount',
        store=True,
    )
    taxable_amount_ut = fields.Float(
        string='Monto Gravable en UT',
        digits=(12, 4),
        compute='_compute_taxable_amount',
        store=True,
    )

    # ------------------------------------------------------------------
    # Resultado de retención
    # ------------------------------------------------------------------
    wh_rate = fields.Float(
        string='Tasa ISLR (%)',
        related='concept_id.wh_rate',
        store=True,
        digits=(5, 4),
    )
    subtract = fields.Float(
        string='Sustraendo (Bs)',
        related='concept_id.subtract',
        store=True,
        digits=(18, 2),
    )
    amount_bs = fields.Monetary(
        string='Monto Retenido (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_wh_amount',
        store=True,
        copy=False,
    )
    amount_usd = fields.Float(
        string='Monto Retenido (USD)',
        digits=(18, 4),
        compute='_compute_wh_amount',
        store=True,
        copy=False,
    )
    amount_ut = fields.Float(
        string='Monto Retenido en UT',
        digits=(12, 4),
        compute='_compute_wh_amount',
        store=True,
    )

    # ------------------------------------------------------------------
    # Monedas
    # ------------------------------------------------------------------
    currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.l10n_ve_currency_bs_id',
        store=True,
    )

    # Asiento contable
    journal_entry_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento Contable',
        copy=False,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Compute: base gravable
    # ------------------------------------------------------------------
    @api.depends('move_id.l10n_ve_amount_untaxed_bs', 'move_id.l10n_ve_rate',
                 'ut_value')
    def _compute_taxable_amount(self):
        for rec in self:
            base_bs = rec.move_id.l10n_ve_amount_untaxed_bs or 0.0
            rate = rec.rate or 1.0
            ut_value = rec.ut_value or 0.0
            rec.taxable_amount_bs = base_bs
            rec.taxable_amount_usd = round(base_bs / rate, 4) if rate else 0.0
            rec.taxable_amount_ut = round(base_bs / ut_value, 4) if ut_value else 0.0

    # ------------------------------------------------------------------
    # Compute: monto de retención
    # ------------------------------------------------------------------
    @api.depends('taxable_amount_bs', 'wh_rate', 'subtract',
                 'calculation_method', 'ut_value', 'rate')
    def _compute_wh_amount(self):
        for rec in self:
            base = rec.taxable_amount_bs
            rate_pct = rec.wh_rate / 100.0
            subtract = rec.subtract
            rate = rec.rate or 1.0
            ut_val = rec.ut_value or 0.0

            if rec.calculation_method == 'percentage':
                amount_bs = round(base * rate_pct, 2)
            elif rec.calculation_method == 'subtract':
                amount_bs = max(round(base * rate_pct - subtract, 2), 0.0)
            elif rec.calculation_method == 'ut_table' and ut_val:
                # Calcula el ISLR en UT y convierte a Bs
                ut_amount = round(rec.taxable_amount_ut * rate_pct, 4)
                amount_bs = round(ut_amount * ut_val, 2)
            else:
                amount_bs = 0.0

            rec.amount_bs = amount_bs
            rec.amount_usd = round(amount_bs / rate, 4) if rate else 0.0
            rec.amount_ut = round(amount_bs / ut_val, 4) if ut_val else 0.0

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_confirm(self):
        for rec in self:
            if rec.name == '/':
                rec.name = self.env['ir.sequence'].next_by_code('account.wh.islr') or '/'
            rec.state = 'confirmed'

    def action_post(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_('Debe confirmar la retención antes de contabilizarla.'))
            if not rec.company_id.l10n_ve_wh_islr_journal_id:
                raise UserError(_('Configure el "Diario Retenciones ISLR" en la compañía.'))
            entry = rec._create_journal_entry()
            rec.journal_entry_id = entry.id
            rec.state = 'posted'

    def _create_journal_entry(self):
        self.ensure_one()
        journal = self.company_id.l10n_ve_wh_islr_journal_id
        account_wh = self.company_id.l10n_ve_wh_islr_account_id
        if not account_wh:
            raise UserError(_('Configure la "Cuenta ISLR Retenido" en la compañía.'))

        move_vals = {
            'move_type': 'entry',
            'date': self.date,
            'journal_id': journal.id,
            'ref': f'Ret. ISLR {self.name} — {self.concept_id.name}',
            'company_id': self.company_id.id,
            'line_ids': [
                (0, 0, {
                    'account_id': account_wh.id,
                    'name': f'ISLR Retenido — {self.name} — {self.partner_id.name}',
                    'debit': self.amount_bs,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                }),
                (0, 0, {
                    'account_id': account_wh.id,
                    'name': f'ISLR por Pagar — {self.name}',
                    'debit': 0.0,
                    'credit': self.amount_bs,
                    'partner_id': self.partner_id.id,
                }),
            ],
        }
        entry = self.env['account.move'].create(move_vals)
        entry.action_post()
        return entry

    def action_cancel(self):
        for rec in self:
            if rec.state == 'posted' and rec.journal_entry_id:
                rec.journal_entry_id.button_cancel()
            rec.state = 'cancel'
