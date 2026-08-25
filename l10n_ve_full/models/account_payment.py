# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de Pagos y Registro de Pagos (account.payment & account.payment.register)
==================================================================================================
Extiende el modal de pago "Pagar" en facturas y la gestión de pagos para incorporar:
  - Tasa de la Factura vs Tasa BCV vs Acuerdo Comercial (Editable)
  - Cálculo automático del monto a pagar en Bs en base al residual en USD
  - Sincronización exacta de tasa y montos USD en apuntes contables y asientos
  - Generación de diferencial cambiario automático por conciliación
  - Opción de Aplicar IGTF (3%) condicionado a monedas extranjeras

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
    l10n_ve_exchange_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento Diferencial Cambiario',
        readonly=True,
        copy=False,
    )
    l10n_ve_exchange_diff_bs = fields.Monetary(
        string='Diferencial Cambiario (Bs)',
        currency_field='l10n_ve_currency_bs_id',
        readonly=True,
        copy=False,
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

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        line_vals_list = super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance
        )
        rate = self.l10n_ve_rate or self.company_id.get_current_bcv_rate() or 779.9522
        bs_currency = self.company_id.l10n_ve_currency_bs_id
        comp_currency = self.company_id.currency_id
        is_pay_bs = (self.currency_id == bs_currency) or (self.currency_id.name in ['VES', 'VEF', 'VEB'])
        comp_is_usd = bool(comp_currency and comp_currency.name in ['USD', '$'])

        if is_pay_bs and comp_is_usd and rate > 0:
            exact_usd = round(self.amount / rate, 2)
            for vals in line_vals_list:
                if vals.get('debit', 0.0) > 0:
                    vals['debit'] = exact_usd
                if vals.get('credit', 0.0) > 0:
                    vals['credit'] = exact_usd
        return line_vals_list

    def action_post(self):
        """Al publicar el pago, propaga la tasa al asiento contable generado y genera diferencial cambiario."""
        for pay in self:
            rate = pay.l10n_ve_rate or pay.company_id.get_current_bcv_rate() or 779.9522
            if pay.move_id and rate > 0:
                pay.move_id.write({
                    'l10n_ve_rate': rate,
                    'l10n_ve_rate_applied': rate,
                    'l10n_ve_rate_type': pay.l10n_ve_rate_type or 'bcv',
                })
        res = super().action_post()
        for pay in self:
            try:
                pay._generate_exchange_difference_entry()
            except Exception as e:
                _logger.warning(f"Error generando diferencial cambiario para pago {pay.name}: {e}")
        return res

    def _synchronize_to_moves(self, changed_fields):
        """Sincroniza la tasa del pago con el asiento contable."""
        res = super()._synchronize_to_moves(changed_fields)
        for pay in self:
            rate = pay.l10n_ve_rate or pay.company_id.get_current_bcv_rate() or 779.9522
            if pay.move_id and rate > 0:
                pay.move_id.write({
                    'l10n_ve_rate': rate,
                    'l10n_ve_rate_applied': rate,
                    'l10n_ve_rate_type': pay.l10n_ve_rate_type or 'bcv',
                })
        return res

    def _generate_exchange_difference_entry(self):
        """Crea automáticamente el asiento contable de Ganancia o Pérdida por Diferencial Cambiario."""
        self.ensure_one()
        if self.l10n_ve_exchange_move_id:
            return self.l10n_ve_exchange_move_id

        # Identificar facturas vinculadas
        invoices = self.reconciled_invoice_ids or self.reconciled_bill_ids
        if not invoices and self.move_id:
            for line in self.move_id.line_ids:
                for matched in line.matched_debit_ids + line.matched_credit_ids:
                    rec_move = matched.debit_move_id.move_id if matched.credit_move_id.move_id == self.move_id else matched.credit_move_id.move_id
                    if rec_move and rec_move.is_invoice() and rec_move not in invoices:
                        invoices |= rec_move

        if not invoices and self._context.get('active_model') == 'account.move' and self._context.get('active_ids'):
            invoices = self.env['account.move'].browse(self._context.get('active_ids')).filtered(lambda m: m.is_invoice())

        if not invoices:
            return False

        pay_rate = self.l10n_ve_rate or self.company_id.get_current_bcv_rate() or 779.9522
        pay_amount_usd = self.l10n_ve_amount_usd or (self.amount / pay_rate if pay_rate else 0.0)

        for inv in invoices:
            inv_rate = inv.l10n_ve_rate_applied or inv.l10n_ve_rate or pay_rate
            if abs(pay_rate - inv_rate) < 0.0001:
                continue

            inv_usd_total = getattr(inv, 'l10n_ve_total_ref', 0.0) or getattr(inv, 'l10n_ve_amount_total_usd', 0.0) or getattr(inv, 'amount_total', 0.0) or pay_amount_usd
            usd_covered = min(pay_amount_usd, inv_usd_total)
            if usd_covered <= 0:
                continue

            bs_at_inv_rate = round(usd_covered * inv_rate, 2)
            bs_at_pay_rate = round(usd_covered * pay_rate, 2)
            diff_bs = round(bs_at_pay_rate - bs_at_inv_rate, 2)

            if abs(diff_bs) < 0.01:
                continue

            is_customer = inv.is_sale_document()
            is_gain = (diff_bs > 0) if is_customer else (diff_bs < 0)
            abs_diff_bs = abs(diff_bs)

            company = self.company_id
            journal = getattr(company, 'currency_exchange_journal_id', False) or self.env['account.journal'].search([
                ('type', '=', 'general'),
                ('company_id', '=', company.id)
            ], limit=1) or self.env['account.journal'].search([('type', '=', 'general')], limit=1)

            if is_gain:
                diff_account = getattr(company, 'income_currency_exchange_account_id', False) or self.env['account.account'].search([
                    ('account_type', 'in', ('income', 'income_other')),
                    ('company_id', '=', company.id),
                    ('name', 'ilike', 'Ganancia')
                ], limit=1) or self.env['account.account'].search([
                    ('account_type', 'in', ('income', 'income_other')),
                    ('company_id', '=', company.id)
                ], limit=1)
            else:
                diff_account = getattr(company, 'expense_currency_exchange_account_id', False) or self.env['account.account'].search([
                    ('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost')),
                    ('company_id', '=', company.id),
                    ('name', 'ilike', 'Pérdida')
                ], limit=1) or self.env['account.account'].search([
                    ('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost')),
                    ('company_id', '=', company.id)
                ], limit=1)

            partner_account = (inv.partner_id.property_account_receivable_id if is_customer else inv.partner_id.property_account_payable_id) or self.env['account.account'].search([
                ('account_type', '=', 'asset_receivable' if is_customer else 'liability_payable'),
                ('company_id', '=', company.id)
            ], limit=1)

            if not journal or not diff_account or not partner_account:
                _logger.warning("No se pudo generar asiento de diferencial cambiario: faltan cuentas o diario.")
                continue

            partner = self.partner_id or inv.partner_id
            desc = f"Diferencial Cambiario: {inv.name} (Tasa Factura {inv_rate:.2f} vs Tasa Pago {pay_rate:.2f})"

            if is_gain:
                lines = [
                    (0, 0, {
                        'name': desc,
                        'partner_id': partner.id,
                        'account_id': partner_account.id,
                        'debit': abs_diff_bs,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': desc,
                        'partner_id': partner.id,
                        'account_id': diff_account.id,
                        'debit': 0.0,
                        'credit': abs_diff_bs,
                    }),
                ]
            else:
                lines = [
                    (0, 0, {
                        'name': desc,
                        'partner_id': partner.id,
                        'account_id': diff_account.id,
                        'debit': abs_diff_bs,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': desc,
                        'partner_id': partner.id,
                        'account_id': partner_account.id,
                        'debit': 0.0,
                        'credit': abs_diff_bs,
                    }),
                ]

            move_vals = {
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': self.date or fields.Date.context_today(self),
                'ref': f"DIF-CAMBIARIO/{inv.name}/{self.name or ''}",
                'l10n_ve_rate_applied': pay_rate,
                'l10n_ve_rate': pay_rate,
                'line_ids': lines,
            }

            try:
                diff_move = self.env['account.move'].create(move_vals)
                diff_move.action_post()
                self.l10n_ve_exchange_move_id = diff_move.id
                self.l10n_ve_exchange_diff_bs = diff_bs
                _logger.info(f"Asiento de diferencial cambiario {diff_move.name} creado por Bs. {diff_bs:,.2f}")
                return diff_move
            except Exception as e:
                _logger.error(f"Error al crear asiento de diferencial cambiario: {e}")

        return False


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
    l10n_ve_currency_usd_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda USD',
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False) or self.env['res.currency'].search([('name', '=', 'USD')], limit=1),
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

    @api.depends('amount', 'payment_date', 'currency_id', 'payment_type', 'line_ids', 'l10n_ve_payment_rate')
    def _compute_payment_difference(self):
        """Evita advertencia de diferencia falsa cuando el pago en Bs cubre el 100% de la divisa de referencia."""
        for wizard in self:
            super(AccountPaymentRegister, wizard)._compute_payment_difference()
            rate = wizard.l10n_ve_payment_rate or wizard.l10n_ve_current_rate or 779.9522
            residual_usd = wizard.l10n_ve_amount_residual_ref or 0.0
            is_bs = wizard.currency_id and wizard.currency_id.name in ['VES', 'VEF', 'VEB']

            if residual_usd > 0 and rate > 0:
                paid_usd = round(wizard.amount / rate, 2) if is_bs else round(wizard.amount, 2)
                if abs(paid_usd - residual_usd) < 0.02:
                    wizard.payment_difference = 0.0
                    wizard.payment_difference_handling = 'open'

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        rate = self.l10n_ve_payment_rate or self.l10n_ve_current_rate or 779.9522
        vals['l10n_ve_rate_type'] = self.l10n_ve_rate_type
        vals['l10n_ve_rate'] = rate
        vals['l10n_ve_apply_igtf'] = self.l10n_ve_apply_igtf
        return vals

    def _create_payments(self):
        payments = super()._create_payments()
        for pay in payments:
            pay._generate_exchange_difference_entry()
        return payments
