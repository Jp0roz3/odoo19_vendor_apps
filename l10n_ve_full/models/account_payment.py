# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de Pagos y Registro de Pagos (account.payment & account.payment.register)
==================================================================================================
Extiende el modal de pago "Pagar" en facturas para incorporar:
  - Tasa de la Factura vs Tasa Actual (del día de pago)
  - Adeudado en Divisa de Referencia (USD $)
  - Opción de Mantener Bs.
  - Opción de Aplicar IGTF (3%)
  - Registro de pagos en moneda dual.

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    l10n_ve_rate = fields.Float(
        string='Tasa del Pago',
        digits=(18, 6),
        help='Tasa BCV registrada para la fecha del pago.',
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
    l10n_ve_currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Bs',
        related='company_id.l10n_ve_currency_bs_id',
    )

    @api.depends('amount', 'currency_id', 'date', 'company_id', 'l10n_ve_rate')
    def _compute_ve_payment_amounts(self):
        for pay in self:
            date = pay.date or fields.Date.context_today(pay)
            rate = pay.l10n_ve_rate or pay.company_id.get_current_bcv_rate() or 60.0
            pay.l10n_ve_rate = rate

            bs_currency = pay.company_id.l10n_ve_currency_bs_id
            is_bs = (pay.currency_id == bs_currency) or (pay.currency_id.name in ['VES', 'VEF', 'VEB'])

            if is_bs:
                pay.l10n_ve_amount_bs = pay.amount
                pay.l10n_ve_amount_usd = round(pay.amount / rate, 2) if rate else 0.0
            else:
                pay.l10n_ve_amount_usd = pay.amount
                pay.l10n_ve_amount_bs = round(pay.amount * rate, 2)


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
        help='Tasa BCV registrada en la factura original.',
    )
    l10n_ve_current_rate = fields.Float(
        string='Tasa Actual',
        compute='_compute_ve_register_duals',
        digits=(18, 6),
        help='Tasa BCV correspondiente a la fecha de pago.',
    )
    l10n_ve_keep_bs = fields.Boolean(
        string='Mantener Bs',
        default=False,
        help='Si está activo, fija el pago en Bolívares manteniendo la equivalencia.',
    )
    l10n_ve_apply_igtf = fields.Boolean(
        string='Aplicar IGTF',
        default=False,
        help='Aplica la retención/cobro del 3% de IGTF por pago en divisas.',
    )

    @api.depends('line_ids', 'payment_date', 'currency_id')
    def _compute_ve_register_duals(self):
        for wizard in self:
            moves = wizard.line_ids.mapped('move_id')
            move = moves[:1] if moves else None
            pay_date = wizard.payment_date or fields.Date.context_today(wizard)

            # Tasa factura
            inv_rate = move.l10n_ve_rate if move and hasattr(move, 'l10n_ve_rate') and move.l10n_ve_rate else 60.0

            # Tasa actual para la fecha de pago
            cur_rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(pay_date, wizard.company_id.id)
            cur_rate = cur_rate_rec.rate if cur_rate_rec and cur_rate_rec.rate > 0 else wizard.company_id.get_current_bcv_rate() or inv_rate

            wizard.l10n_ve_invoice_rate = inv_rate
            wizard.l10n_ve_current_rate = cur_rate

            # Residual en USD
            if move and hasattr(move, 'l10n_ve_residual_ref'):
                wizard.l10n_ve_amount_residual_ref = move.l10n_ve_residual_ref
            else:
                wizard.l10n_ve_amount_residual_ref = abs(sum(wizard.line_ids.mapped('amount_residual')))
