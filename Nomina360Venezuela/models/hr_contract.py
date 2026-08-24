# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta

class HrContract(models.Model):
    _name = 'hr.contract'
    _description = 'Contrato de Trabajo'
    _inherit = ['hr.contract', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Referencia del Contrato", required=True)
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    date_start = fields.Date(string="Fecha de Inicio", required=True, default=fields.Date.today)
    date_end = fields.Date(string="Fecha de Finalización")
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('open', 'En Proceso / Vigente'),
        ('close', 'Expirado / Finalizado'),
        ('cancel', 'Cancelado'),
    ], string="Estado", default='draft')

    wage = fields.Float(string="Salario Base (Bs)", digits=(12, 2))

    wage_currency_type = fields.Selection([
        ('usd', 'Dólares (USD)'),
        ('bs', 'Bolívares (Bs)'),
    ], string="Moneda de Fijación de Salario", default='usd', required=True)

    tasa_bcv = fields.Float(
        string="Tasa BCV Referencial (Bs/USD)",
        digits=(12, 6),
        compute='_compute_tasa_bcv',
        store=True,
        readonly=False,
        help="Tasa oficial BCV o manual aplicada a este contrato de trabajo."
    )

    wage_usd = fields.Float(
        string="Salario en Dólares ($ USD)",
        digits=(12, 2),
        help="Salario base fijado en Dólares americanos."
    )
    wage_bs = fields.Float(
        string="Salario en Bolívares (Bs)",
        digits=(12, 2),
        compute='_compute_wage_bs',
        store=True,
        readonly=False,
        help="Salario equivalente en Bolívares a la tasa de cambio BCV."
    )

    # Bonificación Extra-Patronal No Prestacional (Compensatoria Excluida de Base Imponible)
    bono_extra_patronal_usd = fields.Float(
        string="Bono Compensatorio Extra ($ USD)",
        digits=(12, 2),
        default=0.00,
        help="Asignación extra-patronal no salarial enviada directamente al trabajador."
    )
    bono_extra_patronal_bs = fields.Float(
        string="Bono Compensatorio Extra (Bs)",
        digits=(12, 2),
        compute='_compute_bono_extra_bs',
        store=True,
        readonly=False
    )
    es_no_prestacional = fields.Boolean(
        string="Excluido de Base Salarial LOTTT / IVSS / FAOV (Art. 105)",
        default=True,
        help="Si está marcado, esta asignación no impacta los aportes patronales ni la garantía de prestaciones sociales."
    )

    cesta_ticket_usd = fields.Float(
        string="Bono Alimentación ($ USD)",
        digits=(12, 2),
        default=40.00,
        help="Monto mensual decretado en dólares para Cesta Ticket Socialista."
    )
    cesta_ticket_bs = fields.Float(
        string="Bono Alimentación (Bs)",
        digits=(12, 2),
        compute='_compute_cesta_ticket_bs',
        store=True,
        readonly=False
    )

    days_utilidades = fields.Integer(
        string="Días de Utilidades",
        default=30,
        help="Días de utilidades/aguinaldos anuales acordados (Mínimo 30 días segun Art. 131 LOTTT)."
    )
    days_bono_vacacional = fields.Integer(
        string="Días Bono Vacacional Base",
        default=15,
        help="Días base de bono vacacional (Mínimo 15 días segun Art. 192 LOTTT)."
    )

    salario_integral_bs = fields.Float(
        string="Salario Integral Diario (Bs)",
        digits=(12, 2),
        compute='_compute_salario_integral',
        store=True,
        help="Salario diario + Alícuota de Bono Vacacional + Alícuota de Utilidades."
    )
    salario_integral_usd = fields.Float(
        string="Salario Integral Diario ($ USD)",
        digits=(12, 2),
        compute='_compute_salario_integral',
        store=True
    )

    islr_ari_rate = fields.Float(
        string="Porcentaje Retención ISLR (AR-I %)",
        digits=(5, 2),
        default=0.00,
        help="Porcentaje de retención según planilla AR-I del trabajador."
    )

    has_guarderia = fields.Boolean(string="Aplica Beneficio de Guardería (Art. 343 LOTTT)", default=False)
    num_hijos_guarderia = fields.Integer(string="Número de Hijos en Guardería", default=0)

    antiguedad_years = fields.Integer(
        string="Años de Antigüedad",
        compute='_compute_antiguedad',
        store=True
    )
    antiguedad_months = fields.Integer(
        string="Meses de Antigüedad",
        compute='_compute_antiguedad',
        store=True
    )

    @api.depends('company_id', 'company_id.current_bcv_rate')
    def _compute_tasa_bcv(self):
        for contract in self:
            if not contract.tasa_bcv or contract.tasa_bcv <= 0:
                contract.tasa_bcv = contract.company_id.get_bcv_rate()

    @api.depends('wage_usd', 'wage_currency_type', 'tasa_bcv', 'company_id.current_bcv_rate')
    def _compute_wage_bs(self):
        for contract in self:
            rate = contract.tasa_bcv or contract.company_id.get_bcv_rate() or 1.0
            if contract.wage_currency_type == 'usd':
                contract.wage_bs = round((contract.wage_usd or 0.0) * rate, 2)
                contract.wage = contract.wage_bs
            else:
                contract.wage_bs = contract.wage or 0.0
                if rate > 0:
                    contract.wage_usd = round(contract.wage_bs / rate, 2)

    @api.depends('bono_extra_patronal_usd', 'tasa_bcv', 'company_id.current_bcv_rate')
    def _compute_bono_extra_bs(self):
        for contract in self:
            rate = contract.tasa_bcv or contract.company_id.get_bcv_rate() or 1.0
            contract.bono_extra_patronal_bs = round((contract.bono_extra_patronal_usd or 0.0) * rate, 2)

    schedule_pay = fields.Selection([
        ('semanal', 'Semanal (Obreros / Operativos)'),
        ('quincenal', 'Quincenal (Administrativos / Profesionales)'),
        ('especial', 'Especial (Ejecutivos / Confidencial)'),
    ], string="Frecuencia / Tipo de Nómina", default='quincenal', required=True, help="Define el tipo de nómina al que pertenece el trabajador.")

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string="Centro de Costo / Proyecto",
        help="Cuenta analítica asignada para la distribución de costos de nómina por Proyecto u Obra."
    )

    cesta_ticket_custom_rate = fields.Float(
        string="Tasa Cestaticket Especial (Bs/USD)",
        digits=(12, 6),
        default=0.00,
        help="Tasa especial fijada para este contrato superior a la tasa BCV oficial."
    )

    @api.depends('cesta_ticket_usd', 'cesta_ticket_custom_rate', 'tasa_bcv', 'company_id.cesta_ticket_special_rate', 'company_id.current_bcv_rate')
    def _compute_cesta_ticket_bs(self):
        for contract in self:
            rate = contract.cesta_ticket_custom_rate or contract.company_id.get_bcv_rate(is_cesta_ticket=True) or contract.tasa_bcv or 1.0
            contract.cesta_ticket_bs = round((contract.cesta_ticket_usd or 0.0) * rate, 2)

    @api.depends('date_start')
    def _compute_antiguedad(self):
        today = fields.Date.today()
        for contract in self:
            if contract.date_start:
                delta = relativedelta(today, contract.date_start)
                contract.antiguedad_years = delta.years
                contract.antiguedad_months = delta.months
            else:
                contract.antiguedad_years = 0
                contract.antiguedad_months = 0

    @api.depends('wage_bs', 'wage_usd', 'days_utilidades', 'days_bono_vacacional', 'antiguedad_years')
    def _compute_salario_integral(self):
        for contract in self:
            extra_vac_days = min(max(contract.antiguedad_years - 1, 0), 15)
            total_vac_days = contract.days_bono_vacacional + extra_vac_days

            daily_bs = contract.wage_bs / 30.0 if contract.wage_bs else 0.0
            daily_usd = contract.wage_usd / 30.0 if contract.wage_usd else 0.0

            alicuota_util_bs = (daily_bs * contract.days_utilidades) / 360.0
            alicuota_vac_bs = (daily_bs * total_vac_days) / 360.0

            alicuota_util_usd = (daily_usd * contract.days_utilidades) / 360.0
            alicuota_vac_usd = (daily_usd * total_vac_days) / 360.0

            contract.salario_integral_bs = round(daily_bs + alicuota_util_bs + alicuota_vac_bs, 2)
            contract.salario_integral_usd = round(daily_usd + alicuota_util_usd + alicuota_vac_usd, 2)

    def action_print_contract(self):
        self.ensure_one()
        return self.env.ref('Nomina360Venezuela.action_report_hr_contract_ve').report_action(self)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    contract_id = fields.Many2one('hr.contract', string="Contrato de Trabajo Activo", compute='_compute_contract', store=True)

    @api.depends('name')
    def _compute_contract(self):
        for emp in self:
            contract = self.env['hr.contract'].search([('employee_id', '=', emp.id)], limit=1)
            emp.contract_id = contract.id if contract else False
