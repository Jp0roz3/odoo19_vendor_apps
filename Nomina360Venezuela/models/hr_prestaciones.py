# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrPrestacionesLine(models.Model):
    _name = 'hr.prestaciones.line'
    _description = 'Registro Acumulativo de Prestaciones Sociales (Art. 141-143 LOTTT)'
    _order = 'year desc, quarter desc, id desc'

    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True, ondelete='cascade')
    contract_id = fields.Many2one('hr.contract', string="Contrato", required=True)
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    year = fields.Integer(string="Año", required=True, default=lambda self: fields.Date.today().year)
    quarter = fields.Selection([
        ('1', 'Primer Trimestre (Ene - Mar)'),
        ('2', 'Segundo Trimestre (Abr - Jun)'),
        ('3', 'Tercer Trimestre (Jul - Sep)'),
        ('4', 'Cuarto Trimestre (Oct - Dic)'),
    ], string="Trimestre", required=True)

    salario_integral_bs = fields.Float(string="Salario Integral Diario (Bs)", digits=(12, 2))
    salario_integral_usd = fields.Float(string="Salario Integral Diario ($ USD)", digits=(12, 2))

    dias_garantia = fields.Integer(string="Días de Garantía Trimestral", default=15)
    dias_adicionales = fields.Integer(string="Días Adicionales (Art. 142b)", default=0)

    monto_garantia_trimestre_bs = fields.Float(
        string="Monto Garantía Trimestre (Bs)",
        compute='_compute_garantia',
        store=True,
        digits=(12, 2)
    )
    monto_garantia_acumulada_bs = fields.Float(
        string="Monto Garantía Acumulada (Bs)",
        digits=(12, 2)
    )

    tasa_interes_bcv = fields.Float(
        string="Tasa Interés Pasiva BCV (%)",
        digits=(5, 2),
        default=31.50,
        help="Tasa pasiva promedio fijada mensualmente por el Banco Central de Venezuela."
    )
    intereses_mes_bs = fields.Float(
        string="Intereses del Periodo (Bs)",
        compute='_compute_intereses',
        store=True,
        digits=(12, 2)
    )
    intereses_acumulados_bs = fields.Float(
        string="Intereses Acumulados (Bs)",
        digits=(12, 2)
    )

    anticipos_prestaciones_bs = fields.Float(
        string="Anticipos Otorgados (Bs)",
        digits=(12, 2),
        default=0.00,
        help="Anticipos de prestaciones sociales pagados al trabajador (hasta 75%)."
    )

    saldo_neto_bs = fields.Float(
        string="Saldo Neto Prestaciones (Bs)",
        compute='_compute_saldo_neto',
        store=True,
        digits=(12, 2)
    )
    saldo_neto_usd = fields.Float(
        string="Saldo Neto Prestaciones ($ USD)",
        compute='_compute_saldo_neto',
        store=True,
        digits=(12, 2)
    )
    tasa_bcv = fields.Float(string="Tasa BCV Referencia", digits=(12, 6), default=lambda self: self.env.company.current_bcv_rate)

    @api.depends('salario_integral_bs', 'dias_garantia', 'dias_adicionales')
    def _compute_garantia(self):
        for rec in self:
            total_days = rec.dias_garantia + rec.dias_adicionales
            rec.monto_garantia_trimestre_bs = round((rec.salario_integral_bs or 0.0) * total_days, 2)

    @api.depends('monto_garantia_trimestre_bs', 'tasa_interes_bcv')
    def _compute_intereses(self):
        for rec in self:
            rec.intereses_mes_bs = round((rec.monto_garantia_trimestre_bs * (rec.tasa_interes_bcv / 100.0)) / 4.0, 2)

    @api.depends('monto_garantia_trimestre_bs', 'intereses_mes_bs', 'anticipos_prestaciones_bs', 'tasa_bcv')
    def _compute_saldo_neto(self):
        for rec in self:
            rate = rec.tasa_bcv or rec.env.company.current_bcv_rate or 1.0
            saldo = rec.monto_garantia_trimestre_bs + rec.intereses_mes_bs - rec.anticipos_prestaciones_bs
            rec.saldo_neto_bs = round(max(saldo, 0.0), 2)
            if rate > 0:
                rec.saldo_neto_usd = round(rec.saldo_neto_bs / rate, 2)
            else:
                rec.saldo_neto_usd = 0.0
