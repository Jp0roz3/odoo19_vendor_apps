# -*- coding: utf-8 -*-
"""
Venezuela360: Retención Municipal (account.wh.municipal)
=========================================================
Retención de Impuesto sobre Actividades Económicas (IAE) — Municipal.

Soporta:
- Tasas por municipio y actividad económica
- Comprobante PDF numerado
- Asiento contable automático
- Doble moneda BS/USD con tasa BCV histórica

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountWhMunicipal(models.Model):
    _name = 'account.wh.municipal'
    _description = 'Retención Municipal (IAE) — Venezuela'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(
        string='Número de Comprobante Municipal',
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
    date = fields.Date(
        string='Fecha de Retención',
        required=True,
        default=fields.Date.context_today,
        copy=False,
        tracking=True,
    )

    # ------------------------------------------------------------------
    # Municipio y actividad económica
    # ------------------------------------------------------------------
    municipality_id = fields.Many2one(
        comodel_name='l10n_ve.municipality',
        string='Municipio',
        required=True,
        help='Municipio donde se aplica la retención de IAE.',
    )
    state_ve_id = fields.Many2one(
        comodel_name='l10n_ve.state',
        string='Estado',
        related='municipality_id.state_id',
        store=True,
    )
    economic_activity = fields.Char(
        string='Actividad Económica',
        help='Descripción o código de la actividad económica sujeta a retención.',
    )

    # ------------------------------------------------------------------
    # Tasa y montos
    # ------------------------------------------------------------------
    rate_pct = fields.Float(
        string='Alícuota Municipal (%)',
        required=True,
        digits=(5, 4),
        default=0.0,
        help='Porcentaje de retención municipal (alícuota) según la ordenanza del municipio.',
    )
    taxable_amount_bs = fields.Monetary(
        string='Monto Gravable (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_amounts',
        store=True,
    )
    amount_bs = fields.Monetary(
        string='Monto Retenido (Bs)',
        currency_field='currency_bs_id',
        compute='_compute_amounts',
        store=True,
        copy=False,
    )
    amount_usd = fields.Float(
        string='Monto Retenido (USD)',
        digits=(18, 4),
        compute='_compute_amounts',
        store=True,
        copy=False,
    )
    rate = fields.Float(
        string='Tasa BCV (Bs/USD)',
        related='move_id.l10n_ve_rate',
        store=True,
        digits=(18, 6),
    )
    currency_bs_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.l10n_ve_currency_bs_id',
        store=True,
    )

    journal_entry_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento Contable',
        copy=False,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('move_id.l10n_ve_amount_untaxed_bs', 'rate_pct', 'rate', 'move_id.l10n_ve_rate')
    def _compute_amounts(self):
        for rec in self:
            doc_rate = rec.move_id.l10n_ve_rate or rec.move_id.l10n_ve_rate_applied or rec.rate or (rec.company_id.get_current_bcv_rate() if hasattr(rec.company_id, 'get_current_bcv_rate') else 779.9522) or 779.9522
            rec.rate = doc_rate
            base_bs = rec.move_id.l10n_ve_amount_untaxed_bs or 0.0
            rec.taxable_amount_bs = base_bs
            rec.amount_bs = round(base_bs * rec.rate_pct / 100.0, 2)
            rec.amount_usd = round(rec.amount_bs / doc_rate, 2) if doc_rate else 0.0

    @api.onchange('municipality_id')
    def _onchange_municipality(self):
        """Sugerir la tasa de retención del municipio seleccionado."""
        if self.municipality_id:
            self.rate_pct = self.municipality_id.wh_municipal_rate
            if self.move_id and self.move_id.partner_id.l10n_ve_municipal_rate:
                # Priorizar la tasa del partner si está configurada
                self.rate_pct = self.move_id.partner_id.l10n_ve_municipal_rate

    @api.constrains('rate_pct')
    def _check_rate(self):
        for rec in self:
            if not (0.0 <= rec.rate_pct <= 100.0):
                raise ValidationError(_('La alícuota municipal debe estar entre 0% y 100%.'))

    def action_confirm(self):
        for rec in self:
            if rec.name == '/':
                rec.name = self.env['ir.sequence'].next_by_code('account.wh.municipal') or '/'
            rec.state = 'confirmed'
        return True

    def action_post(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_('Debe confirmar la retención antes de contabilizarla.'))
            if not rec.company_id.l10n_ve_wh_municipal_journal_id:
                raise UserError(_('Configure el "Diario Retenciones Municipales" en la compañía.'))
            entry = rec._create_journal_entry()
            rec.journal_entry_id = entry.id
            rec.state = 'posted'
        return True

    def _create_journal_entry(self):
        self.ensure_one()
        journal = self.company_id.l10n_ve_wh_municipal_journal_id
        account_wh = self.company_id.l10n_ve_wh_municipal_account_id
        if not account_wh:
            raise UserError(_('Configure la "Cuenta Ret. Municipal" en la compañía.'))

        # Débito: Cuenta por Pagar del proveedor en la factura origen
        invoice_payable_lines = self.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in (
                'liability_payable', 'asset_receivable'
            )
        )
        if not invoice_payable_lines:
            raise UserError(_(
                'La factura no tiene línea de cuentas por pagar/cobrar. '
                'Verifique que la factura esté correctamente configurada.'
            ))
        payable_account = invoice_payable_lines[0].account_id

        comp_currency = self.company_id.currency_id
        comp_is_usd = bool(comp_currency and comp_currency.name in ['USD', '$'])
        doc_rate = self.move_id.l10n_ve_rate or self.move_id.l10n_ve_rate_applied or self.rate or (self.company_id.get_current_bcv_rate() if hasattr(self.company_id, 'get_current_bcv_rate') else 779.9522) or 779.9522

        if comp_is_usd:
            debit_usd = round(self.amount_usd or (self.amount_bs / doc_rate if doc_rate else 0.0), 2)
            credit_usd = debit_usd
        else:
            debit_usd = self.amount_bs
            credit_usd = self.amount_bs

        move_vals = {
            'move_type': 'entry',
            'date': self.date,
            'journal_id': journal.id,
            'ref': f'Ret. Municipal {self.name} — Municipio {self.municipality_id.name}',
            'company_id': self.company_id.id,
            'l10n_ve_rate': doc_rate,
            'l10n_ve_rate_applied': doc_rate,
            'l10n_ve_rate_type': self.move_id.l10n_ve_rate_type or 'bcv',
            'line_ids': [
                # DÉBITO: Reduce la CxP al proveedor
                (0, 0, {
                    'account_id': payable_account.id,
                    'name': f'IAE Ret. — {self.name} — {self.partner_id.name}',
                    'debit': debit_usd,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                }),
                # CRÉDITO: Registra IAE por pagar al Municipio
                (0, 0, {
                    'account_id': account_wh.id,
                    'name': f'IAE Por Pagar — {self.municipality_id.name}',
                    'debit': 0.0,
                    'credit': credit_usd,
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
