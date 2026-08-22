# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de Pagos y Registro de Pagos (account.payment & account.payment.register)
==================================================================================================
Extiende el modal de pago "Pagar" en facturas para incorporar:
  - Tasa de la Factura vs Tasa BCV vs Acuerdo Comercial (Editable)
  - Cálculo automático del monto a pagar en Bs en base al residual en USD
  - Opción de Aplicar IGTF (3%) condicionado a monedas extranjeras
  - Generación de diferencial cambiario automático por conciliación
  - Bloqueo readonly de IGTF en pagos confirmados.

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    l10n_ve_rate_type = fields.Selection(
        selection=[
            ('invoice', 'Tasa Factura'),
            ('bcv', 'Tasa Oficial BCV'),
            ('commercial', 'Acuerdo Comercial'),
        ],
        string='Tipo de Tasa Pago',
        default='bcv',
    )
    l10n_ve_rate = fields.Float(
        string='Tasa del Pago',
        digits=(18, 6),
        help='Tasa BCV o comercial registrada para la fecha del pago.',
    )
    l10n_ve_amount_bs = fields.Monetary(
        string='Monto Pago (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        compute='_compute_ve_payment_amounts',
        store=True,
    )
    l10n_ve_amount_usd = fields.Float(
        string='Monto Pago ($)',
        digits=(18, 2),
        compute='_compute_ve_payment_amounts',
        store=True,
    )
    l10n_ve_apply_igtf = fields.Boolean(
        string='Aplicar IGTF (3%)',
        default=False,
    )
    l10n_ve_igtf_amount = fields.Monetary(
        string='Monto IGTF (3%)',
        currency_field='currency_id',
        compute='_compute_ve_payment_amounts',
        store=True,
    )
    l10n_ve_currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Bs',
        related='company_id.l10n_ve_currency_bs_id',
    )

    @api.depends('amount', 'currency_id', 'date', 'company_id', 'l10n_ve_rate', 'l10n_ve_apply_igtf')
    def _compute_ve_payment_amounts(self):
        for pay in self:
            rate = pay.l10n_ve_rate or pay.company_id.get_current_bcv_rate() or 779.9522
            pay.l10n_ve_rate = rate

            bs_currency = pay.company_id.l10n_ve_currency_bs_id
            is_bs = (pay.currency_id == bs_currency) or (pay.currency_id.name in ['VES', 'VEF', 'VEB'])

            if is_bs:
                pay.l10n_ve_amount_bs = pay.amount
                pay.l10n_ve_amount_usd = round(pay.amount / rate, 2) if rate else 0.0
            else:
                pay.l10n_ve_amount_usd = pay.amount
                pay.l10n_ve_amount_bs = round(pay.amount * rate, 2)

            if pay.l10n_ve_apply_igtf and pay.amount:
                pay.l10n_ve_igtf_amount = round(pay.amount * 0.03, 2)
            else:
                pay.l10n_ve_igtf_amount = 0.0


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    l10n_ve_amount_residual_ref = fields.Float(
        string='Adeudado Divisa Ref.',
        compute='_compute_ve_register_duals',
        digits=(18, 2),
        help='Monto adeudado de la factura en divisa de referencia (USD).',
    )
    l10n_ve_invoice_rate = fields.Float(
        string='Tasa Factura',
        compute='_compute_ve_register_duals',
        digits=(18, 6),
        help='Tasa registrada en la factura original.',
    )
    l10n_ve_current_rate = fields.Float(
        string='Tasa Actual',
        compute='_compute_ve_register_duals',
        digits=(18, 6),
        help='Tasa BCV correspondiente a la fecha de pago.',
    )
    l10n_ve_rate_type = fields.Selection(
        selection=[
            ('invoice', 'Tasa Factura'),
            ('bcv', 'Tasa BCV Actual'),
            ('commercial', 'Acuerdo Comercial / Otra Tasa'),
        ],
        string='Tipo de Tasa Pago',
        default='bcv',
        required=True,
    )
    l10n_ve_payment_rate = fields.Float(
        string='Tasa Pago Aplicada',
        digits=(18, 6),
        compute='_compute_ve_payment_rate',
        store=True,
        readonly=False,
    )
    l10n_ve_keep_bs = fields.Boolean(
        string='Mantener Bs',
        default=False,
        help='Si está activo, fija el pago en Bolívares manteniendo la equivalencia.',
    )
    l10n_ve_apply_igtf = fields.Boolean(
        string='Aplicar IGTF (3%)',
        default=False,
        help='Aplica el cobro/percepción del 3% de IGTF por pago en divisas.',
    )
    l10n_ve_is_foreign_currency = fields.Boolean(
        string='Es Moneda Extranjera',
        compute='_compute_ve_is_foreign_currency',
    )

    @api.depends('currency_id')
    def _compute_ve_is_foreign_currency(self):
        for wizard in self:
            wizard.l10n_ve_is_foreign_currency = wizard.currency_id and wizard.currency_id.name not in ['VES', 'VEF', 'VEB']

    @api.depends('line_ids', 'payment_date', 'currency_id')
    def _compute_ve_register_duals(self):
        for wizard in self:
            moves = wizard.line_ids.mapped('move_id')
            move = moves[:1] if moves else None
            pay_date = wizard.payment_date or fields.Date.context_today(wizard)

            # Tasa factura
            inv_rate = move.l10n_ve_rate_applied or move.l10n_ve_rate if move and hasattr(move, 'l10n_ve_rate') and move.l10n_ve_rate else 779.9522

            # Tasa actual para la fecha de pago
            cur_rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(pay_date, wizard.company_id.id)
            cur_rate = cur_rate_rec.rate if cur_rate_rec and cur_rate_rec.rate > 0 else wizard.company_id.get_current_bcv_rate() or inv_rate

            wizard.l10n_ve_invoice_rate = inv_rate
            wizard.l10n_ve_current_rate = cur_rate

            # Residual en USD
            if move and hasattr(move, 'l10n_ve_residual_ref') and move.l10n_ve_residual_ref:
                wizard.l10n_ve_amount_residual_ref = move.l10n_ve_residual_ref
            else:
                wizard.l10n_ve_amount_residual_ref = abs(sum(wizard.line_ids.mapped('amount_residual')))

    @api.depends('l10n_ve_rate_type', 'l10n_ve_invoice_rate', 'l10n_ve_current_rate')
    def _compute_ve_payment_rate(self):
        for wizard in self:
            if wizard.l10n_ve_rate_type == 'invoice':
                wizard.l10n_ve_payment_rate = wizard.l10n_ve_invoice_rate or 779.9522
            elif wizard.l10n_ve_rate_type == 'bcv':
                wizard.l10n_ve_payment_rate = wizard.l10n_ve_current_rate or 779.9522
            elif not wizard.l10n_ve_payment_rate or wizard.l10n_ve_payment_rate <= 0:
                wizard.l10n_ve_payment_rate = wizard.l10n_ve_current_rate or 779.9522

    @api.onchange('l10n_ve_rate_type', 'l10n_ve_payment_rate', 'currency_id', 'journal_id', 'line_ids')
    def _onchange_ve_rate_and_amount(self):
        """Calcula dinámicamente el monto a pagar en Bs a partir del saldo residual en USD."""
        for wizard in self:
            rate = wizard.l10n_ve_payment_rate or wizard.l10n_ve_current_rate or 779.9522
            is_bs = wizard.currency_id and wizard.currency_id.name in ['VES', 'VEF', 'VEB']
            residual_usd = wizard.l10n_ve_amount_residual_ref or 0.0

            if is_bs and residual_usd > 0:
                wizard.amount = round(residual_usd * rate, 2)
            elif not is_bs and residual_usd > 0:
                wizard.amount = residual_usd

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        vals['l10n_ve_rate_type'] = self.l10n_ve_rate_type
        vals['l10n_ve_rate'] = self.l10n_ve_payment_rate or self.l10n_ve_current_rate or 779.9522
        vals['l10n_ve_apply_igtf'] = self.l10n_ve_apply_igtf
        return vals
