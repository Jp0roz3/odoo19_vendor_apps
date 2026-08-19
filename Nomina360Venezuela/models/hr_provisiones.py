# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrPayrollProvision(models.Model):
    _name = 'hr.payroll.provision'
    _description = 'Registro y Asiento Contable de Provisiones Mensuales (Utilidades, Vacaciones, Prestaciones)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, id desc'

    name = fields.Char(string="Código de Provisión", required=True, copy=False, readonly=True, default=lambda self: _('Nuevo'))
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company, required=True)
    year = fields.Integer(string="Año Fiscal", required=True, default=lambda self: fields.Date.today().year)
    month = fields.Selection([
        ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'),
        ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'),
        ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre')
    ], string="Mes", required=True)

    tasa_bcv = fields.Float(string="Tasa BCV del Mes", digits=(12, 6), default=lambda self: self.env.company.get_bcv_rate())
    utilidades_days_convention = fields.Selection([
        ('60', '60 Días de Utilidades'),
        ('100', '100 Días de Utilidades'),
        ('110', '110 Días de Utilidades'),
        ('120', '120 Días de Utilidades (Máximo Legal)'),
    ], string="Convención de Utilidades", default='60', required=True)

    total_provision_utilidades_bs = fields.Float(string="Provisión Utilidades (Bs)", compute='_compute_provisiones', store=True, digits=(12, 2))
    total_provision_vacaciones_bs = fields.Float(string="Provisión Vacaciones & Bono (Bs)", compute='_compute_provisiones', store=True, digits=(12, 2))
    total_provision_prestaciones_bs = fields.Float(string="Provisión Prestaciones Sociales (Bs)", compute='_compute_provisiones', store=True, digits=(12, 2))
    total_provision_intereses_bs = fields.Float(string="Provisión Intereses Prestaciones (Bs)", compute='_compute_provisiones', store=True, digits=(12, 2))

    total_provision_mes_bs = fields.Float(string="TOTAL PROVISIÓN MES (Bs)", compute='_compute_provisiones', store=True, digits=(12, 2))
    total_provision_mes_usd = fields.Float(string="TOTAL PROVISIÓN MES ($ USD)", compute='_compute_provisiones', store=True, digits=(12, 2))

    move_id = fields.Many2one('account.move', string="Asiento Contable de Provisión", readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Borrador / Calculado'),
        ('posted', 'Contabilizado'),
    ], string="Estado", default='draft', tracking=True)

    line_ids = fields.One2many('hr.payroll.provision.line', 'provision_id', string="Detalle por Empleado")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.payroll.provision') or _('PROV-%s') % fields.Date.today().strftime('%Y%m')
        return super(HrPayrollProvision, self).create(vals_list)

    @api.onchange('year', 'month', 'utilidades_days_convention')
    def action_compute_sheet(self):
        for rec in self:
            rec.line_ids.unlink()
            employees = self.env['hr.employee'].search([('active', '=', True), ('company_id', '=', rec.company_id.id)])
            days_util = int(rec.utilidades_days_convention or '60')

            lines = []
            for emp in employees:
                contract = emp.contract_id or self.env['hr.contract'].search([('employee_id', '=', emp.id), ('state', '=', 'open')], limit=1)
                if not contract:
                    continue

                wage_bs = contract.wage_bs or 0.0
                salario_diario = wage_bs / 30.0
                salario_integral = contract.salario_integral_bs or (salario_diario * 1.15)

                # Alícuotas mensuales
                prov_util = round((salario_diario * days_util) / 12.0, 2)
                dias_vac = 15 + min(max(contract.antiguedad_years - 1, 0), 15)
                dias_bono_vac = 15 + min(max(contract.antiguedad_years - 1, 0), 15)
                prov_vac = round((salario_diario * (dias_vac + dias_bono_vac)) / 12.0, 2)
                prov_prest = round(salario_integral * 5.0, 2)  # 5 días mensuales equivalentes a 15 días trimestrales
                prov_int = round(prov_prest * 0.02625, 2)     # ~31.5% anual / 12

                lines.append((0, 0, {
                    'employee_id': emp.id,
                    'contract_id': contract.id,
                    'analytic_account_id': contract.analytic_account_id.id if contract.analytic_account_id else False,
                    'wage_bs': wage_bs,
                    'salario_integral_bs': salario_integral,
                    'provision_utilidades_bs': prov_util,
                    'provision_vacaciones_bs': prov_vac,
                    'provision_prestaciones_bs': prov_prest,
                    'provision_intereses_bs': prov_int,
                }))

            rec.write({'line_ids': lines})

    @api.depends('line_ids.provision_utilidades_bs', 'line_ids.provision_vacaciones_bs', 'line_ids.provision_prestaciones_bs', 'line_ids.provision_intereses_bs', 'tasa_bcv')
    def _compute_provisiones(self):
        for rec in self:
            u = sum(rec.line_ids.mapped('provision_utilidades_bs'))
            v = sum(rec.line_ids.mapped('provision_vacaciones_bs'))
            p = sum(rec.line_ids.mapped('provision_prestaciones_bs'))
            i = sum(rec.line_ids.mapped('provision_intereses_bs'))

            rec.total_provision_utilidades_bs = round(u, 2)
            rec.total_provision_vacaciones_bs = round(v, 2)
            rec.total_provision_prestaciones_bs = round(p, 2)
            rec.total_provision_intereses_bs = round(i, 2)

            tot_bs = u + v + p + i
            rec.total_provision_mes_bs = round(tot_bs, 2)
            rate = rec.tasa_bcv or 1.0
            rec.total_provision_mes_usd = round(tot_bs / rate, 2) if rate > 0 else 0.0

    def action_generate_accounting_move(self):
        for rec in self:
            if rec.move_id:
                continue

            journal = self.env['account.journal'].search([('type', '=', 'general'), ('company_id', '=', rec.company_id.id)], limit=1)
            if not journal:
                journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)

            acc_expense = self.env['account.account'].search([('account_type', 'in', ('expense', 'expense_direct_cost'))], limit=1)
            acc_provision_pass = self.env['account.account'].search([('account_type', 'in', ('liability_current', 'liability_non_current'))], limit=1)

            if not journal or not acc_expense or not acc_provision_pass:
                raise UserError(_("No se encontraron las cuentas contables o el diario general necesario para generar el asiento de provisión."))

            move_lines = []
            for line in rec.line_ids:
                tot_emp = line.provision_utilidades_bs + line.provision_vacaciones_bs + line.provision_prestaciones_bs + line.provision_intereses_bs
                if tot_emp <= 0:
                    continue

                dist = {str(line.analytic_account_id.id): 100.0} if line.analytic_account_id else False
                line_exp = {
                    'name': f'Gasto Provisión Prestaciones & Beneficios - {line.employee_id.name}',
                    'account_id': acc_expense.id,
                    'debit': round(tot_emp, 2),
                    'credit': 0.0,
                }
                if dist:
                    line_exp['analytic_distribution'] = dist
                move_lines.append((0, 0, line_exp))

            # Credit Total Provision Liability
            move_lines.append((0, 0, {
                'name': f'Pasivo Acumulado Provisiones Nómina - {rec.name}',
                'account_id': acc_provision_pass.id,
                'debit': 0.0,
                'credit': rec.total_provision_mes_bs,
            }))

            move = self.env['account.move'].create({
                'ref': f'PROVISIÓN-NOMINA-{rec.name}',
                'journal_id': journal.id,
                'date': fields.Date.today(),
                'line_ids': move_lines,
            })
            move.action_post()
            rec.write({'move_id': move.id, 'state': 'posted'})


class HrPayrollProvisionLine(models.Model):
    _name = 'hr.payroll.provision.line'
    _description = 'Línea de Provisión por Empleado'

    provision_id = fields.Many2one('hr.payroll.provision', string="Provisión", ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    contract_id = fields.Many2one('hr.contract', string="Contrato", required=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string="Centro de Costo")

    wage_bs = fields.Float(string="Sueldo Base (Bs)", digits=(12, 2))
    salario_integral_bs = fields.Float(string="Salario Integral (Bs)", digits=(12, 2))

    provision_utilidades_bs = fields.Float(string="Utilidades (Bs)", digits=(12, 2))
    provision_vacaciones_bs = fields.Float(string="Vacaciones & Bono (Bs)", digits=(12, 2))
    provision_prestaciones_bs = fields.Float(string="Prestaciones (Bs)", digits=(12, 2))
    provision_intereses_bs = fields.Float(string="Intereses (Bs)", digits=(12, 2))
