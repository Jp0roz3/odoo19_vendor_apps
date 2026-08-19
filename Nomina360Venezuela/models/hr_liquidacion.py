# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, date

class HrLiquidacion(models.Model):
    _name = 'hr.liquidacion'
    _description = 'Calculadora de Liquidación de Finiquito (LOTTT Art. 142 y Art. 92)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Referencia Liquidación", required=True, copy=False, readonly=True, default=lambda self: _('Nuevo'))
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True, tracking=True)
    contract_id = fields.Many2one('hr.contract', string="Contrato", required=True)
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    date_start = fields.Date(string="Fecha de Ingrese", required=True)
    date_end = fields.Date(string="Fecha de Egreso", required=True, default=fields.Date.today)

    antiguedad_years = fields.Integer(string="Años de Antigüedad", compute='_compute_antiguedad', store=True)
    antiguedad_months = fields.Integer(string="Meses de Antigüedad Fraccionados", compute='_compute_antiguedad', store=True)

    cause = fields.Selection([
        ('despido_injustificado', 'Despido Injustificado (Aplica Doble Indemnización Art. 92)'),
        ('despido_justificado', 'Despido Justificado (Art. 79 LOTTT)'),
        ('renuncia', 'Renuncia Voluntaria (Art. 80 LOTTT)'),
        ('vencimiento_contrato', 'Vencimiento de Contrato a Tiempo Determinado'),
    ], string="Causa de Retiro", required=True, default='renuncia', tracking=True)

    salario_base_mensual_bs = fields.Float(string="Salario Base Mensual (Bs)", digits=(12, 2))
    salario_integral_diario_bs = fields.Float(string="Salario Integral Diario (Bs)", digits=(12, 2))

    tasa_bcv = fields.Float(string="Tasa BCV al Egreso", digits=(12, 6), default=lambda self: self.env.company.current_bcv_rate)

    # Regla del Mayor (Art. 142 LOTTT)
    monto_garantia_acumulada_bs = fields.Float(string="Opción A: Garantía Trimestral Acumulada (Bs)", digits=(12, 2))
    monto_retroactivo_art142c_bs = fields.Float(string="Opción B: Retroactivo 30 Días/Año (Bs)", compute='_compute_retroactivo', store=True, digits=(12, 2))

    monto_prestaciones_final_bs = fields.Float(
        string="Monto Prestaciones a Pagar (Regla del Mayor Art. 142 LOTTT)",
        compute='_compute_prestaciones_final',
        store=True,
        digits=(12, 2),
        tracking=True
    )

    # Indemnizaciones Art. 92 y Art. 80
    aplica_doble_indemnizacion = fields.Boolean(string="Aplica Doble Indemnización (Art. 92)", default=False)
    monto_indemnizacion_art92_bs = fields.Float(string="Indemnización por Despido Art. 92 (Bs)", compute='_compute_indemnizacion', store=True, digits=(12, 2))
    monto_preaviso_art80_bs = fields.Float(string="Indemnización por Preaviso Art. 80/81 (Bs)", digits=(12, 2), default=0.00)

    # Conceptos Pendientes
    vacaciones_pendientes_bs = fields.Float(string="Vacaciones Pendientes/Fraccionadas (Bs)", digits=(12, 2), default=0.00)
    bono_vacacional_pendiente_bs = fields.Float(string="Bono Vacacional Pendiente/Fraccionado (Bs)", digits=(12, 2), default=0.00)
    utilidades_fraccionadas_bs = fields.Float(string="Utilidades Fraccionadas (Bs)", digits=(12, 2), default=0.00)

    total_liquidacion_bs = fields.Float(
        string="TOTAL NETO LIQUIDACIÓN (Bs)",
        compute='_compute_total_liquidacion',
        store=True,
        digits=(12, 2)
    )
    total_liquidacion_usd = fields.Float(
        string="TOTAL NETO LIQUIDACIÓN ($ USD)",
        compute='_compute_total_liquidacion',
        store=True,
        digits=(12, 2)
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('calculated', 'Calculado'),
        ('approved', 'Aprobado y Pagado'),
        ('cancel', 'Cancelado'),
    ], string="Estado", default='draft', tracking=True)

    @api.depends('date_start', 'date_end')
    def _compute_antiguedad(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                d1 = rec.date_start
                d2 = rec.date_end
                days = (d2 - d1).days
                rec.antiguedad_years = days // 365
                rec.antiguedad_months = (days % 365) // 30
            else:
                rec.antiguedad_years = 0
                rec.antiguedad_months = 0

    @api.depends('salario_integral_diario_bs', 'antiguedad_years', 'antiguedad_months')
    def _compute_retroactivo(self):
        for rec in self:
            # Art 142 c: 30 días de salario por cada año de servicio o fracción superior a 6 meses
            total_years = rec.antiguedad_years
            if rec.antiguedad_months >= 6:
                total_years += 1
            rec.monto_retroactivo_art142c_bs = round((rec.salario_integral_diario_bs or 0.0) * 30 * total_years, 2)

    @api.depends('monto_garantia_acumulada_bs', 'monto_retroactivo_art142c_bs')
    def _compute_prestaciones_final(self):
        for rec in self:
            # Regla del Mayor: Se paga lo que resulte mayor entre Garantía Acumulada y Retroactivo
            rec.monto_prestaciones_final_bs = max(rec.monto_garantia_acumulada_bs or 0.0, rec.monto_retroactivo_art142c_bs or 0.0)

    @api.depends('cause', 'monto_prestaciones_final_bs', 'aplica_doble_indemnizacion')
    def _compute_indemnizacion(self):
        for rec in self:
            if rec.cause == 'despido_injustificado' or rec.aplica_doble_indemnizacion:
                # Art 92: Indemnización equivalente al monto de las prestaciones sociales
                rec.monto_indemnizacion_art92_bs = rec.monto_prestaciones_final_bs
            else:
                rec.monto_indemnizacion_art92_bs = 0.0

    @api.depends('monto_prestaciones_final_bs', 'monto_indemnizacion_art92_bs', 'monto_preaviso_art80_bs',
                 'vacaciones_pendientes_bs', 'bono_vacacional_pendiente_bs', 'utilidades_fraccionadas_bs', 'tasa_bcv')
    def _compute_total_liquidacion(self):
        for rec in self:
            total_bs = (
                rec.monto_prestaciones_final_bs +
                rec.monto_indemnizacion_art92_bs +
                rec.monto_preaviso_art80_bs +
                rec.vacaciones_pendientes_bs +
                rec.bono_vacacional_pendiente_bs +
                rec.utilidades_fraccionadas_bs
            )
            rec.total_liquidacion_bs = round(total_bs, 2)
            rate = rec.tasa_bcv or rec.env.company.current_bcv_rate or 1.0
            if rate > 0:
                rec.total_liquidacion_usd = round(total_bs / rate, 2)
            else:
                rec.total_liquidacion_usd = 0.0

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', self.employee_id.id),
                ('state', '=', 'open')
            ], limit=1)
            if contract:
                self.contract_id = contract.id
                self.date_start = contract.date_start
                self.salario_base_mensual_bs = contract.wage_bs
                self.salario_integral_diario_bs = contract.salario_integral_bs

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.liquidacion') or _('Nuevo')
        return super(HrLiquidacion, self).create(vals_list)

    def action_calculate(self):
        for rec in self:
            if rec.contract_id:
                rec.salario_base_mensual_bs = rec.contract_id.wage_bs
                rec.salario_integral_diario_bs = rec.contract_id.salario_integral_bs
                rec.date_start = rec.contract_id.date_start
            rec.state = 'calculated'

    def action_approve(self):
        for rec in self:
            rec.state = 'approved'
            if rec.contract_id:
                rec.contract_id.write({'state': 'close', 'date_end': rec.date_end})
