# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import calendar
from datetime import datetime, timedelta

class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _description = 'Recibo de Nómina Venezuela'
    _inherit = ['hr.payslip', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Referencia", default=lambda self: _('Nuevo'))
    number = fields.Char(string="Número de Recibo", readonly=True)
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    contract_id = fields.Many2one('hr.contract', string="Contrato", required=True)
    payslip_run_id = fields.Many2one('hr.payslip.run', string="Lote de Nómina", ondelete='cascade')
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    date_from = fields.Date(string="Fecha Desde", required=True, default=fields.Date.today)
    date_to = fields.Date(string="Fecha Hasta", required=True, default=fields.Date.today)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('verify', 'Verificado'),
        ('done', 'Hecho'),
        ('cancel', 'Cancelado'),
    ], string="Estado", default='draft', tracking=True)

    line_ids = fields.One2many('hr.payslip.line', 'slip_id', string="Líneas del Recibo", copy=True)

    tasa_bcv = fields.Float(
        string="Tasa BCV del Recibo (USD/Bs)",
        digits=(12, 6),
        compute='_compute_tasa_bcv',
        store=True,
        readonly=False,
        help="Tasa oficial BCV aplicada para el cálculo del recibo de nómina."
    )
    total_bs = fields.Float(
        string="Total en Bolívares (Bs)",
        compute='_compute_dual_currency_totals',
        store=True,
        digits=(12, 2)
    )
    total_usd = fields.Float(
        string="Total en Dólares ($ USD)",
        compute='_compute_dual_currency_totals',
        store=True,
        digits=(12, 2)
    )
    net_wage_bs = fields.Float(
        string="Salario Neto (Bs)",
        compute='_compute_dual_currency_totals',
        store=True,
        digits=(12, 2)
    )
    net_wage_usd = fields.Float(
        string="Salario Neto ($ USD)",
        compute='_compute_dual_currency_totals',
        store=True,
        digits=(12, 2)
    )
    lunes_del_mes = fields.Integer(
        string="Número de Lunes en el Período",
        compute='_compute_lunes_del_mes',
        store=True,
        help="Cantidad exacta de lunes contenidos en el rango de fechas del recibo para cálculo legal de IVSS y SPF."
    )

    is_out_of_cycle = fields.Boolean(
        string="Nómina Fuera de Ciclo",
        default=False,
        help="Indica si el recibo corresponde a un pago especial o fuera del ciclo quincenal/mensual."
    )

    @api.depends('payslip_run_id', 'payslip_run_id.tasa_bcv', 'company_id')
    def _compute_tasa_bcv(self):
        for slip in self:
            if slip.payslip_run_id and slip.payslip_run_id.tasa_bcv > 0:
                slip.tasa_bcv = slip.payslip_run_id.tasa_bcv
            elif not slip.tasa_bcv or slip.tasa_bcv <= 0:
                slip.tasa_bcv = slip.company_id.get_bcv_rate()

    @api.depends('date_from', 'date_to')
    def _compute_lunes_del_mes(self):
        for payslip in self:
            if payslip.date_from and payslip.date_to:
                current_date = payslip.date_from
                mondays = 0
                while current_date <= payslip.date_to:
                    if current_date.weekday() == 0:  # 0 is Monday
                        mondays += 1
                    current_date += timedelta(days=1)
                payslip.lunes_del_mes = max(mondays, 1)
            else:
                payslip.lunes_del_mes = 2

    @api.depends('line_ids.total', 'tasa_bcv')
    def _compute_dual_currency_totals(self):
        for payslip in self:
            rate = payslip.tasa_bcv or payslip.company_id.get_bcv_rate() or 1.0
            
            net_line = payslip.line_ids.filtered(lambda l: l.code == 'NET')
            net_val = sum(net_line.mapped('total')) if net_line else sum(payslip.line_ids.mapped('total'))

            payslip.total_bs = round(sum(payslip.line_ids.filtered(lambda l: l.category_id.code in ('BASIC', 'ALW')).mapped('total')), 2)
            payslip.net_wage_bs = round(net_val, 2)

            if rate > 0:
                payslip.total_usd = round(payslip.total_bs / rate, 2)
                payslip.net_wage_usd = round(payslip.net_wage_bs / rate, 2)
            else:
                payslip.total_usd = 0.0
                payslip.net_wage_usd = 0.0

    def compute_sheet(self):
        for payslip in self:
            payslip.line_ids.unlink()
            rules = self.env['hr.salary.rule'].search([], order='sequence, id')
            lines = []

            # Python execution namespace context
            categories = type('Categories', (), {})()
            setattr(categories, 'BASIC', 0.0)
            setattr(categories, 'ALW', 0.0)
            setattr(categories, 'DED', 0.0)
            setattr(categories, 'PAT', 0.0)
            setattr(categories, 'NET', 0.0)

            localdict = {
                'payslip': payslip,
                'employee': payslip.employee_id,
                'contract': payslip.contract_id,
                'categories': categories,
                'result': 0.0,
            }

            for rule in rules:
                condition_ok = True
                if rule.condition_select == 'python' and rule.condition_python:
                    try:
                        eval(compile(rule.condition_python, '<string>', 'exec'), localdict)
                        condition_ok = bool(localdict.get('result', True))
                    except Exception:
                        condition_ok = False

                if condition_ok:
                    amount = 0.0
                    if rule.amount_select == 'fix':
                        amount = rule.amount_fix
                    elif rule.amount_select == 'code' and rule.amount_python_compute:
                        try:
                            eval(compile(rule.amount_python_compute, '<string>', 'exec'), localdict)
                            amount = float(localdict.get('result', 0.0))
                        except Exception:
                            amount = 0.0

                    cat_code = rule.category_id.code
                    current_cat = getattr(categories, cat_code, 0.0)
                    setattr(categories, cat_code, current_cat + amount)

                    lines.append((0, 0, {
                        'name': rule.name,
                        'code': rule.code,
                        'category_id': rule.category_id.id,
                        'sequence': rule.sequence,
                        'total': round(amount, 2),
                    }))

            # 1. Bonificación Extra-Patronal Compensatoria No Prestacional
            if payslip.contract_id and payslip.contract_id.bono_extra_patronal_bs > 0:
                cat_alw = self.env['hr.salary.rule.category'].search([('code', '=', 'ALW')], limit=1)
                monto_extra = payslip.contract_id.bono_extra_patronal_bs / 2.0  # Quincenal
                if cat_alw:
                    lines.append((0, 0, {
                        'name': 'Bonificación Compensatoria Extra (No Salarial / Art. 105)',
                        'code': 'BONO_EXTRA',
                        'category_id': cat_alw.id,
                        'sequence': 25,
                        'total': round(monto_extra, 2),
                    }))

            # 2. Descuento de Cuota de Préstamos / Adelantos Activos
            loans = self.env['hr.loan'].search([
                ('employee_id', '=', payslip.employee_id.id),
                ('state', '=', 'approved'),
                ('saldo_pendiente_bs', '>', 0)
            ])
            for loan in loans:
                unpaid_line = loan.line_ids.filtered(lambda l: not l.pagado)
                if unpaid_line:
                    line_to_pay = unpaid_line[0]
                    cat_ded = self.env['hr.salary.rule.category'].search([('code', '=', 'DED')], limit=1)
                    if cat_ded:
                        lines.append((0, 0, {
                            'name': f'Descuento Cuota Préstamo ({line_to_pay.name})',
                            'code': 'DED_PRESTAMO',
                            'category_id': cat_ded.id,
                            'sequence': 95,
                            'total': -abs(round(line_to_pay.monto_bs, 2)),
                        }))

            payslip.write({'line_ids': lines, 'state': 'verify'})

    def action_payslip_done(self):
        for payslip in self:
            payslip.write({'state': 'done'})
            payslip._sync_prestaciones_sociales()
            payslip._sync_loan_deductions()

    def _sync_loan_deductions(self):
        self.ensure_one()
        loans = self.env['hr.loan'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'approved'),
            ('saldo_pendiente_bs', '>', 0)
        ])
        for loan in loans:
            unpaid_lines = loan.line_ids.filtered(lambda l: not l.pagado)
            if unpaid_lines:
                line_to_pay = unpaid_lines[0]
                line_to_pay.write({
                    'pagado': True,
                    'fecha_pago': self.date_to or fields.Date.today(),
                    'payslip_id': self.id,
                })
                # Check if loan fully paid
                if loan.saldo_pendiente_bs <= 0:
                    loan.write({'state': 'paid'})

    def action_print_payslip(self):
        return self.env.ref('Nomina360Venezuela.action_report_payslip_ve').report_action(self)

    def _sync_prestaciones_sociales(self):
        self.ensure_one()
        if self.contract_id and self.contract_id.salario_integral_bs > 0:
            prestaciones_model = self.env['hr.prestaciones.line']
            quarter_val = (self.date_to.month - 1) // 3 + 1
            quarter_str = str(int(quarter_val))
            year_val = int(self.date_to.year)
            domain = [
                ('employee_id', '=', self.employee_id.id),
                ('year', '=', year_val),
                ('quarter', '=', quarter_str)
            ]
            exist = prestaciones_model.search(domain, limit=1)
            if not exist:
                prestaciones_model.create({
                    'employee_id': self.employee_id.id,
                    'contract_id': self.contract_id.id,
                    'year': year_val,
                    'quarter': quarter_str,
                    'salario_integral_bs': self.contract_id.salario_integral_bs,
                    'salario_integral_usd': self.contract_id.salario_integral_usd,
                    'dias_garantia': 15,
                    'dias_adicionales': min(max(self.contract_id.antiguedad_years - 1, 0), 30),
                    'tasa_bcv': self.tasa_bcv,
                })


class HrPayslipLine(models.Model):
    _name = 'hr.payslip.line'
    _description = 'Línea de Recibo de Nómina'
    _order = 'sequence, id'

    slip_id = fields.Many2one('hr.payslip', string="Recibo", ondelete='cascade', required=True)
    name = fields.Char(string="Concepto", required=True)
    code = fields.Char(string="Código", required=True)
    category_id = fields.Many2one('hr.salary.rule.category', string="Categoría", required=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    total = fields.Float(string="Total (Bs)", digits=(12, 2))
