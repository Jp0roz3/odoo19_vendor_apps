# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrLoan(models.Model):
    _name = 'hr.loan'
    _description = 'Préstamos y Adelantos de Nómina Venezuela'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string="Código de Préstamo", required=True, copy=False, readonly=True, default=lambda self: _('Nuevo'))
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True, tracking=True)
    contract_id = fields.Many2one('hr.contract', string="Contrato", compute='_compute_contract_id', store=True)
    date = fields.Date(string="Fecha de Solicitud", required=True, default=fields.Date.today, tracking=True)
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    tasa_bcv = fields.Float(
        string="Tasa BCV de la Operación (Bs/USD)",
        digits=(12, 6),
        default=lambda self: self.env.company.get_bcv_rate(),
        help="Tasa de cambio BCV al momento de otorgar el préstamo."
    )

    currency_type = fields.Selection([
        ('usd', 'Dólares ($ USD)'),
        ('bs', 'Bolívares (Bs)'),
    ], string="Moneda del Préstamo", default='usd', required=True, tracking=True)

    payment_frequency = fields.Selection([
        ('quincenal', 'Quincenal'),
        ('mensual', 'Mensual'),
    ], string="Frecuencia de Descuento", default='quincenal', required=True)

    monto_solicitado_usd = fields.Float(string="Monto Solicitado ($ USD)", digits=(12, 2), tracking=True)
    monto_solicitado_bs = fields.Float(string="Monto Solicitado (Bs)", digits=(12, 2), tracking=True)

    numero_cuotas = fields.Integer(string="Número de Cuotas", default=2, required=True, help="Cantidad de períodos (quincenas o meses) para amortizar el préstamo.")
    monto_cuota_usd = fields.Float(string="Cuota por Período ($ USD)", compute='_compute_cuotas', store=True, digits=(12, 2))
    monto_cuota_bs = fields.Float(string="Cuota por Período (Bs)", compute='_compute_cuotas', store=True, digits=(12, 2))

    total_pagado_bs = fields.Float(string="Total Pagado (Bs)", compute='_compute_saldos', store=True, digits=(12, 2))
    saldo_pendiente_bs = fields.Float(string="Saldo Pendiente (Bs)", compute='_compute_saldos', store=True, digits=(12, 2))
    saldo_pendiente_usd = fields.Float(string="Saldo Pendiente ($ USD)", compute='_compute_saldos', store=True, digits=(12, 2))

    motivo = fields.Text(string="Motivo / Justificación del Préstamo")

    line_ids = fields.One2many('hr.loan.line', 'loan_id', string="Tabla de Amortización / Cuotas")

    state = fields.Selection([
        ('draft', 'Borrador / Solicitado'),
        ('approved', 'Aprobado y Activo'),
        ('paid', 'Pagado Totalmente'),
        ('cancel', 'Cancelado / Rechazado'),
    ], string='Estado', index=True, readonly=True, copy=False, default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.loan') or _('PRES-%s') % fields.Date.today().strftime('%Y%m%d')
        return super(HrLoan, self).create(vals_list)

    @api.depends('employee_id')
    def _compute_contract_id(self):
        for loan in self:
            if loan.employee_id:
                loan.contract_id = loan.employee_id.contract_id or self.env['hr.contract'].search([('employee_id', '=', loan.employee_id.id), ('state', '=', 'open')], limit=1)
            else:
                loan.contract_id = False

    @api.onchange('monto_solicitado_usd', 'monto_solicitado_bs', 'currency_type', 'tasa_bcv')
    def _onchange_montos_currency(self):
        rate = self.tasa_bcv or self.env.company.get_bcv_rate() or 1.0
        if self.currency_type == 'usd':
            if self.monto_solicitado_usd > 0:
                self.monto_solicitado_bs = round(self.monto_solicitado_usd * rate, 2)
        else:
            if self.monto_solicitado_bs > 0 and rate > 0:
                self.monto_solicitado_usd = round(self.monto_solicitado_bs / rate, 2)

    @api.depends('monto_solicitado_usd', 'monto_solicitado_bs', 'numero_cuotas')
    def _compute_cuotas(self):
        for loan in self:
            cuotas = loan.numero_cuotas if loan.numero_cuotas > 0 else 1
            loan.monto_cuota_usd = round((loan.monto_solicitado_usd or 0.0) / cuotas, 2)
            loan.monto_cuota_bs = round((loan.monto_solicitado_bs or 0.0) / cuotas, 2)

    @api.depends('monto_solicitado_bs', 'monto_solicitado_usd', 'line_ids.pagado', 'line_ids.monto_bs', 'tasa_bcv')
    def _compute_saldos(self):
        for loan in self:
            pagado_bs = sum(line.monto_bs for line in loan.line_ids if line.pagado)
            loan.total_pagado_bs = round(pagado_bs, 2)
            saldo_bs = round((loan.monto_solicitado_bs or 0.0) - pagado_bs, 2)
            loan.saldo_pendiente_bs = max(0.0, saldo_bs)
            rate = loan.tasa_bcv or 1.0
            loan.saldo_pendiente_usd = round(loan.saldo_pendiente_bs / rate, 2) if rate > 0 else 0.0

            if loan.state == 'approved' and loan.saldo_pendiente_bs <= 0.0 and len(loan.line_ids) > 0:
                loan.state = 'paid'

    def action_approve(self):
        for loan in self:
            if loan.monto_solicitado_usd <= 0:
                raise UserError(_("El monto del préstamo debe ser mayor a 0."))
            loan.write({'state': 'approved'})
            loan._generate_amortization_table()

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def _generate_amortization_table(self):
        for loan in self:
            loan.line_ids.unlink()
            cuotas = loan.numero_cuotas if loan.numero_cuotas > 0 else 1
            rate = loan.tasa_bcv or 1.0
            cuota_usd = round(loan.monto_solicitado_usd / cuotas, 2)
            cuota_bs = round(loan.monto_solicitado_bs / cuotas, 2)

            lines = []
            for i in range(1, cuotas + 1):
                lines.append((0, 0, {
                    'name': f'Cuota {i} de {cuotas} - {loan.name}',
                    'numero_cuota': i,
                    'monto_usd': cuota_usd,
                    'monto_bs': cuota_bs,
                    'pagado': False,
                }))
            loan.write({'line_ids': lines})

    def action_print_loan_receipt(self):
        self.ensure_one()
        return self.env.ref('Nomina360Venezuela.action_report_loan_receipt').report_action(self)


class HrLoanLine(models.Model):
    _name = 'hr.loan.line'
    _description = 'Línea / Cuota de Amortización de Préstamo'

    loan_id = fields.Many2one('hr.loan', string="Préstamo", ondelete='cascade')
    name = fields.Char(string="Descripción", required=True)
    numero_cuota = fields.Integer(string="N° Cuota", required=True)
    monto_usd = fields.Float(string="Monto ($ USD)", digits=(12, 2))
    monto_bs = fields.Float(string="Monto (Bs)", digits=(12, 2))
    payslip_id = fields.Many2one('hr.payslip', string="Recibo de Nómina", readonly=True)
    pagado = fields.Boolean(string="¿Descontado en Nómina?", default=False)
    fecha_pago = fields.Date(string="Fecha de Descuento")
