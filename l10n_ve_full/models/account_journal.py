# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de account.journal
===========================================
Dashboard de Contabilidad bimoneda: USD en ROJO / Bs. en NEGRO.

ESTRATEGIA FINAL (2 capas):
  1. Python: _get_journal_dashboard_data_batched agrega los campos _bs
     para TODOS los tipos de diario (Ventas, Compras, Banco, Efectivo, Tarjeta, etc.):
       · sale/purchase: sum_waiting_bs, sum_draft_bs, sum_late_bs
       · bank/cash/credit: account_balance_bs, outstanding_pay_balance_bs, last_balance_bs

  2. QWeb (account_journal_dashboard_views.xml): xpath position='replace'
     reemplaza cada span monetario con:
       · span #1 color:#dc3545 (ROJO)   → valor USD
       · span #2 color:#1a1a1a (NEGRO)  → valor Bs. via
         JSON.parse(record.kanban_dashboard.raw_value).<campo>_bs

Autor: JeanPerozo / Nubelco
"""
import re
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # ------------------------------------------------------------------ #
    #  Helpers de formato venezolano                                       #
    # ------------------------------------------------------------------ #
    def _format_ve_bs(self, amount, symbol='Bs.'):
        """Formatea un monto al estilo venezolano: 180.360,54 Bs."""
        formatted = f"{amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"{formatted} {symbol}"

    def _get_ve_rate_and_symbol(self, company, today):
        """Obtiene la tasa BCV y el símbolo Bs. para una compañía."""
        bs_currency = getattr(company, 'l10n_ve_currency_bs_id', None)
        symbol_bs = bs_currency.symbol if bs_currency else 'Bs.'

        rate_bcv = 777.4161  # fallback BCV actual
        if bs_currency:
            rate_rec = self.env['res.currency.rate'].search([
                ('currency_id', '=', bs_currency.id),
                ('name', '<=', today),
            ], order='name desc', limit=1)
            if rate_rec and rate_rec.rate > 0:
                rate_bcv = rate_rec.rate if rate_rec.rate > 1.0 else (1.0 / rate_rec.rate)
            else:
                # Buscar en l10n_ve.exchange.rate
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
            company = journal.company_id
            if not getattr(company, 'l10n_ve_active', False) or \
               not getattr(company, 'l10n_ve_dual_currency', False):
                continue

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

                data['sum_waiting_bs'] = self._format_ve_bs(
                    sum(open_moves.mapped('l10n_ve_amount_total_bs')), symbol_bs)
                data['sum_draft_bs'] = self._format_ve_bs(
                    sum(draft_moves.mapped('l10n_ve_amount_total_bs')), symbol_bs)
                data['sum_late_bs'] = self._format_ve_bs(
                    sum(late_moves.mapped('l10n_ve_amount_total_bs')), symbol_bs)

            # ── DIARIOS BANCO / EFECTIVO / TARJETA ──────────────────────
            elif journal.type in ('bank', 'cash', 'credit'):
                # 1. Balance de cuenta principal en Bs.
                journal_acc_id = journal.default_account_id.id if journal.default_account_id else False
                if journal_acc_id:
                    acc_lines = self.env['account.move.line'].search([
                        ('account_id', '=', journal_acc_id),
                        ('parent_state', '=', 'posted'),
                    ])
                    acc_bs = sum(l.l10n_ve_debit_bs - l.l10n_ve_credit_bs for l in acc_lines)
                else:
                    acc_bs = 0.0

                # 2. Balance de pagos pendientes en Bs.
                out_lines = self.env['account.move.line'].search([
                    ('journal_id', '=', journal.id),
                    ('parent_state', '=', 'posted'),
                    ('full_reconcile_id', '=', False),
                    ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable', 'asset_current', 'liability_current']),
                ])
                out_bs = sum(abs(l.l10n_ve_debit_bs - l.l10n_ve_credit_bs) for l in out_lines)

                # Fallback en caso de que out_bs sea 0 pero haya monto formateado en USD
                if out_bs == 0.0 and data.get('outstanding_pay_account_balance'):
                    raw_str = data['outstanding_pay_account_balance']
                    clean_str = re.sub(r'[^\d.,]', '', raw_str)
                    if clean_str:
                        # si hay coma decimal o punto
                        clean_num = clean_str.replace('.', '').replace(',', '.') if ',' in clean_str else clean_str
                        try:
                            val_num = float(clean_num)
                            out_bs = val_num * rate_bcv
                        except ValueError:
                            out_bs = 0.0

                data['account_balance_bs'] = self._format_ve_bs(acc_bs, symbol_bs)
                data['outstanding_pay_balance_bs'] = self._format_ve_bs(out_bs, symbol_bs)
                data['last_balance_bs'] = self._format_ve_bs(
                    (journal.last_statement_id.balance_end_real if journal.last_statement_id else 0.0) * rate_bcv,
                    symbol_bs
                )

            data['l10n_ve_dual_active'] = True

        return dashboard_data
