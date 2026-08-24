# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    name = fields.Char(string="Nombre del Período", required=True)
    date_start = fields.Date(string="Fecha Inicio", required=True, default=fields.Date.today)
    date_end = fields.Date(string="Fecha Fin", required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    slip_ids = fields.One2many('hr.payslip', 'payslip_run_id', string="Recibos de Nómina")

    tasa_bcv = fields.Float(
        string="Tasa BCV del Lote (USD/Bs)",
        digits=(12, 6),
        default=lambda self: self.env.company.get_bcv_rate(),
        help="Tasa de cambio BCV aplicada a todo el lote de recibos de nómina."
    )

    @api.onchange('date_end', 'date_start')
    def _onchange_dates_tasa_bcv(self):
        target_date = self.date_end or self.date_start or fields.Date.context_today(self)
        if self.company_id:
            self.tasa_bcv = self.company_id.get_bcv_rate(date=target_date)
    total_bs = fields.Float(
        string="Total Neto en Bolívares (Bs)",
        compute='_compute_lote_totals',
        store=True,
        digits=(12, 2)
    )
    total_usd = fields.Float(
        string="Total Neto en Dólares ($ USD)",
        compute='_compute_lote_totals',
        store=True,
        digits=(12, 2)
    )
    costo_empleador_bs = fields.Float(
        string="Costo Total Empleador (Bs)",
        compute='_compute_lote_totals',
        store=True,
        digits=(12, 2)
    )

    move_id = fields.Many2one('account.move', string="Asiento Contable de Nómina", readonly=True, copy=False)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('verify', 'Listo'),
        ('close', 'Hecho'),
        ('paid', 'Pagado'),
    ], string='Estado', index=True, readonly=True, copy=False, default='draft', tracking=True)

    @api.onchange('tasa_bcv')
    def _onchange_tasa_bcv(self):
        if self.tasa_bcv > 0:
            for slip in self.slip_ids:
                slip.tasa_bcv = self.tasa_bcv

    @api.depends('slip_ids.net_wage_bs', 'slip_ids.tasa_bcv', 'tasa_bcv')
    def _compute_lote_totals(self):
        for run in self:
            rate = run.tasa_bcv or run.env.company.get_bcv_rate() or 1.0
            total_net_bs = sum(run.slip_ids.mapped('net_wage_bs'))
            run.total_bs = round(total_net_bs, 2)
            if rate > 0:
                run.total_usd = round(total_net_bs / rate, 2)
            else:
                run.total_usd = 0.0
            
            run.costo_empleador_bs = round(sum(run.slip_ids.mapped('total_bs')), 2)

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_verify(self):
        self.write({'state': 'verify'})

    def action_close(self):
        self.write({'state': 'close'})
        for slip in self.slip_ids:
            if slip.state != 'done':
                slip.action_payslip_done()
        self._generate_payroll_accounting_entry()

    def action_paid(self):
        self.write({'state': 'paid'})

    def action_open_journal_entry(self):
        self.ensure_one()
        if self.move_id:
            return {
                'name': _('Asiento Contable de Nómina'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': self.move_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    payroll_type = fields.Selection([
        ('semanal', 'Nómina Semanal (Obreros)'),
        ('quincenal', 'Nómina Quincenal (Administrativos)'),
        ('especial', 'Nómina Especial (Confidencial / Ejecutiva)'),
    ], string="Tipo de Nómina", default='quincenal', required=True)

    def _generate_payroll_accounting_entry(self):
        for run in self:
            if run.move_id:
                continue

            journal = self.env['account.journal'].search([('type', '=', 'general'), ('company_id', '=', run.company_id.id)], limit=1)
            if not journal:
                journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
            
            if not journal:
                continue

            # Find or get expense and payable accounts
            acc_expense = self.env['account.account'].search([('account_type', 'in', ('expense', 'expense_direct_cost'))], limit=1)
            if not acc_expense:
                acc_expense = self.env['account.account'].search([('code', '=like', '6%')], limit=1)
            
            acc_payable = self.env['account.account'].search([('account_type', 'in', ('liability_payable', 'liability_current'))], limit=1)
            if not acc_payable:
                acc_payable = self.env['account.account'].search([('code', '=like', '2%')], limit=1)

            if not acc_expense or not acc_payable:
                continue

            total_net_bs = run.total_bs or 1.0
            seniat_9_bs = round(total_net_bs * 0.09, 2)

            move_lines = []
            # Group expense lines by Analytic Account (Centro de Costo) if assigned
            slips_by_analytic = {}
            for slip in run.slip_ids:
                analytic = slip.contract_id.analytic_account_id if slip.contract_id else False
                an_id = analytic.id if analytic else 0
                slips_by_analytic.setdefault(an_id, 0.0)
                slips_by_analytic[an_id] += slip.net_wage_bs

            for an_id, net_amount in slips_by_analytic.items():
                if net_amount <= 0:
                    continue
                dist = {str(an_id): 100.0} if an_id else False
                line_data = {
                    'name': f'Gasto Sueldos y Salarios - {run.name}',
                    'account_id': acc_expense.id,
                    'debit': round(net_amount, 2),
                    'credit': 0.0,
                }
                if dist:
                    line_data['analytic_distribution'] = dist
                move_lines.append((0, 0, line_data))

                # SENIAT 9% Expense line per cost center
                line_seniat = {
                    'name': f'Aporte SENIAT Pensiones 9% - {run.name}',
                    'account_id': acc_expense.id,
                    'debit': round(net_amount * 0.09, 2),
                    'credit': 0.0,
                }
                if dist:
                    line_seniat['analytic_distribution'] = dist
                move_lines.append((0, 0, line_seniat))

            # Credit Lines: Liabilities
            move_lines.append((0, 0, {
                'name': f'Sueldos y Salarios por Pagar - {run.name}',
                'account_id': acc_payable.id,
                'debit': 0.0,
                'credit': total_net_bs,
            }))
            move_lines.append((0, 0, {
                'name': f'Pasivo SENIAT Ley Pensiones 9% - {run.name}',
                'account_id': acc_payable.id,
                'debit': 0.0,
                'credit': seniat_9_bs,
            }))

            move = self.env['account.move'].create({
                'ref': f'NÓMINA-VE-{run.name}',
                'journal_id': journal.id,
                'date': run.date_end or fields.Date.today(),
                'line_ids': move_lines,
            })
            move.action_post()
            run.move_id = move.id

