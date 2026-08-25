# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de account.journal
===========================================
Dashboard de Contabilidad bimoneda: USD en ROJO ($) / Bs. en NEGRO.
Coincidencia exacta con la Imagen 2 de referencia:
  $ 2,78 / 1.490,02 Bs.F

Autor: JeanPerozo / Nubelco
"""
import re
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_ve_control_sequence_id = fields.Many2one(
        comodel_name='l10n_ve.control.sequence',
        string='Talonario de Control Fiscal SENIAT',
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        help='Talonario de control fiscal predeterminado para este diario.',
    )

    # ------------------------------------------------------------------ #
    #  Helpers de formato venezolano                                       #
    # ------------------------------------------------------------------ #
    def _format_ve_bs(self, amount, symbol='Bs.F'):
        """Formatea un monto al estilo venezolano: 1.490,02 Bs.F"""
        formatted = f"{amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"{formatted} {symbol}"

    def _format_ve_usd(self, amount):
        """Formatea un monto al estilo Dólares: $ 2,78"""
        formatted = f"{amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"$ {formatted}"

    def _get_ve_rate_and_symbol(self, company, today):
        """Obtiene la tasa BCV y el símbolo Bs. para una compañía."""
        bs_currency = getattr(company, 'l10n_ve_currency_bs_id', None)
        symbol_bs = bs_currency.symbol if bs_currency else 'Bs.F'

        rate_bcv = 777.4161  # fallback BCV actual
        if bs_currency:
            rate_rec = self.env['res.currency.rate'].search([
                ('currency_id', '=', bs_currency.id),
                ('name', '<=', today),
            ], order='name desc', limit=1)
            if rate_rec and rate_rec.rate > 0:
                rate_bcv = rate_rec.rate if rate_rec.rate > 1.0 else (1.0 / rate_rec.rate)
            else:
                rate_ve = self.env['l10n_ve.exchange.rate'].get_rate_for_date(today, company_id=company.id)
                if rate_ve and rate_ve.rate > 0:
                    rate_bcv = rate_ve.rate
        return rate_bcv, symbol_bs

    # ------------------------------------------------------------------ #
    #  Override del método que construye los datos del dashboard           #
    # ------------------------------------------------------------------ #
    def _get_journal_dashboard_data_batched(self):
        dashboard_data = super()._get_journal_dashboard_data_batched()
        today = fields.Date.context_today(self)

        for journal in self:
            company = journal.company_id or self.env.company

            data = dashboard_data.get(journal.id)
            if not data:
                continue

            rate_bcv, symbol_bs = self._get_ve_rate_and_symbol(company, today)

            # ── DIARIOS VENTA / COMPRA ─────────────────────────────────
            if journal.type in ('sale', 'purchase'):
                open_moves = self.env['account.move'].search([
                    ('journal_id', '=', journal.id),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ['not_paid', 'partial']),
                    ('company_id', '=', company.id),
                ])
                draft_moves = self.env['account.move'].search([
                    ('journal_id', '=', journal.id),
                    ('state', '=', 'draft'),
                    ('company_id', '=', company.id),
                ])
                late_moves = open_moves.filtered(
                    lambda m: m.invoice_date_due and m.invoice_date_due < today
                )

                # Calcular total en USD
                sum_waiting_usd_val = sum(
                    m.amount_total if m.currency_id.name == 'USD' else (m.l10n_ve_amount_total_bs / rate_bcv if rate_bcv else m.amount_total)
                    for m in open_moves
                )
                sum_draft_usd_val = sum(
                    m.amount_total if m.currency_id.name == 'USD' else (m.l10n_ve_amount_total_bs / rate_bcv if rate_bcv else m.amount_total)
                    for m in draft_moves
                )
                sum_late_usd_val = sum(
                    m.amount_total if m.currency_id.name == 'USD' else (m.l10n_ve_amount_total_bs / rate_bcv if rate_bcv else m.amount_total)
                    for m in late_moves
                )

                # Montos en USD (ROJO)
                data['sum_waiting_usd'] = self._format_ve_usd(sum_waiting_usd_val)
                data['sum_draft_usd'] = self._format_ve_usd(sum_draft_usd_val)
                data['sum_late_usd'] = self._format_ve_usd(sum_late_usd_val)

                # Montos en Bs. (NEGRO)
                data['sum_waiting_bs'] = self._format_ve_bs(sum(open_moves.mapped('l10n_ve_amount_total_bs')), symbol_bs)
                data['sum_draft_bs'] = self._format_ve_bs(sum(draft_moves.mapped('l10n_ve_amount_total_bs')), symbol_bs)
                data['sum_late_bs'] = self._format_ve_bs(sum(late_moves.mapped('l10n_ve_amount_total_bs')), symbol_bs)

            # ── DIARIOS BANCO / EFECTIVO / TARJETA ──────────────────────
            elif journal.type in ('bank', 'cash', 'credit'):
                journal_curr = journal.currency_id or company.currency_id
                is_journal_usd = journal_curr and journal_curr.name in ['USD', '$']

                journal_acc_id = journal.default_account_id.id if journal.default_account_id else False
                if journal_acc_id:
                    acc_lines = self.env['account.move.line'].search([
                        ('account_id', '=', journal_acc_id),
                        ('parent_state', '=', 'posted'),
                    ])
                    if is_journal_usd:
                        acc_usd = sum(l.debit - l.credit for l in acc_lines)
                        acc_bs = round(acc_usd * rate_bcv, 2)
                    else:
                        acc_bs = sum(l.l10n_ve_debit_bs - l.l10n_ve_credit_bs for l in acc_lines) or sum(l.debit - l.credit for l in acc_lines)
                        acc_usd = round(acc_bs / rate_bcv, 2) if rate_bcv else 0.0
                else:
                    acc_bs = 0.0
                    acc_usd = 0.0

                out_lines = self.env['account.move.line'].search([
                    ('journal_id', '=', journal.id),
                    ('parent_state', '=', 'posted'),
                    ('full_reconcile_id', '=', False),
                    ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable', 'asset_current', 'liability_current']),
                ])
                if is_journal_usd:
                    out_usd = sum(abs(l.debit - l.credit) for l in out_lines)
                    out_bs = round(out_usd * rate_bcv, 2)
                else:
                    out_bs = sum(abs(l.l10n_ve_debit_bs - l.l10n_ve_credit_bs) for l in out_lines) or sum(abs(l.debit - l.credit) for l in out_lines)
                    out_usd = round(out_bs / rate_bcv, 2) if rate_bcv else 0.0

                if is_journal_usd:
                    last_bal_usd = round((journal.last_statement_id.balance_end_real if journal.last_statement_id else 0.0), 2)
                    last_bal_bs = round(last_bal_usd * rate_bcv, 2)
                else:
                    last_bal_bs = round((journal.last_statement_id.balance_end_real if journal.last_statement_id else 0.0), 2)
                    last_bal_usd = round(last_bal_bs / rate_bcv, 2) if rate_bcv else 0.0

                data['account_balance_usd'] = self._format_ve_usd(acc_usd)
                data['outstanding_pay_balance_usd'] = self._format_ve_usd(out_usd)
                data['last_balance_usd'] = self._format_ve_usd(last_bal_usd)

                data['account_balance_bs'] = self._format_ve_bs(acc_bs, symbol_bs)
                data['outstanding_pay_balance_bs'] = self._format_ve_bs(out_bs, symbol_bs)
                data['last_balance_bs'] = self._format_ve_bs(last_bal_bs, symbol_bs)

            data['l10n_ve_dual_active'] = True

        return dashboard_data


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    l10n_ve_rate = fields.Float(
        string='Tasa Transacción (Bs/USD)',
        digits=(18, 6),
        help='Tasa de cambio aplicada a la transacción bancaria.',
    )
    l10n_ve_amount_usd = fields.Float(
        string='Importe ($)',
        compute='_compute_ve_statement_usd',
        store=True,
        digits=(18, 2),
    )

    @api.depends('amount', 'l10n_ve_rate', 'currency_id', 'journal_id')
    def _compute_ve_statement_usd(self):
        for st_line in self:
            company = getattr(st_line, 'company_id', False) or getattr(st_line.journal_id, 'company_id', False) or self.env.company
            rate = st_line.l10n_ve_rate or (company.get_current_bcv_rate() if hasattr(company, 'get_current_bcv_rate') else 779.9522) or 779.9522
            if not st_line.l10n_ve_rate:
                st_line.l10n_ve_rate = rate
            is_bs = st_line.currency_id and st_line.currency_id.name in ['VES', 'VEF', 'VEB']
            if is_bs and rate:
                st_line.l10n_ve_amount_usd = round(st_line.amount / rate, 2)
            else:
                st_line.l10n_ve_amount_usd = st_line.amount

    def _sync_ve_move_lines(self):
        """Sincroniza la tasa y montos USD del asiento generado por la transacción bancaria."""
        for st_line in self:
            move = getattr(st_line, 'move_id', False)
            if not move:
                continue
            rate = st_line.l10n_ve_rate or (st_line.company_id.get_current_bcv_rate() if hasattr(st_line.company_id, 'get_current_bcv_rate') else 779.9522) or 779.9522
            move.write({
                'l10n_ve_rate': rate,
                'l10n_ve_rate_applied': rate,
            })
            comp_currency = st_line.company_id.currency_id
            bs_currency = getattr(st_line.company_id, 'l10n_ve_currency_bs_id', False)
            is_st_bs = (st_line.currency_id == bs_currency) or (st_line.currency_id.name in ['VES', 'VEF', 'VEB'])
            comp_is_usd = bool(comp_currency and comp_currency.name in ['USD', '$'])

            if is_st_bs and comp_is_usd and rate > 0:
                exact_usd = round(abs(st_line.amount) / rate, 2)
                for line in move.line_ids:
                    line_vals = {}
                    if line.debit > 0 and abs(line.debit - exact_usd) > 0.001:
                        line_vals['debit'] = exact_usd
                    if line.credit > 0 and abs(line.credit - exact_usd) > 0.001:
                        line_vals['credit'] = exact_usd
                    if line_vals:
                        line.write(line_vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_ve_move_lines()
        return records

    def write(self, vals):
        if 'l10n_ve_rate' in vals:
            for st_line in self:
                if getattr(st_line, 'is_reconciled', False) and abs((st_line.l10n_ve_rate or 0.0) - (vals['l10n_ve_rate'] or 0.0)) > 0.000001:
                    raise UserError(_('No se puede modificar la tasa de cambio de una transacción bancaria que ya ha sido conciliada.'))
        res = super().write(vals)
        self._sync_ve_move_lines()
        return res

