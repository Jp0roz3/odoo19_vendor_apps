# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError
import base64
from datetime import datetime

class HrPayslipTodoticket(models.Model):
    _name = 'hr.payslip.todoticket'
    _check_company_auto = True
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Abono Masivo TXT TodoTicket (Cestaticket)'
    _order = 'id desc'

    name = fields.Char(
        string='Referencia / NRO.', required=True, copy=False, readonly=True,
        index=True, default=lambda self: _('Nuevo'))

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Realizado'),
        ('cancel', 'Cancelado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company)

    company_code = fields.Char(
        string='Código de Empresa TodoTicket', required=True, default='1234',
        help='Código asignado oficialmente por TodoTicket a la empresa (ej: 1234)')

    date_payment = fields.Date(
        string='Fecha de Abono', required=True, default=fields.Date.today,
        help='Fecha oficial en que se acreditará el monto en la tarjeta TodoTicket')

    tasa_bcv = fields.Float(
        string='Tasa BCV Referencia (USD/Bs)', digits=(12, 6),
        default=lambda self: self.env.company.get_bcv_rate(),
        help='Tasa BCV aplicada para el cálculo equivalente en dólares.')

    payslip_run_ids = fields.Many2many(
        'hr.payslip.run', string='Lotes de Nómina',
        help='Seleccione los lotes de nómina a incluir en el abono de Cestaticket')

    line_ids = fields.One2many(
        'hr.payslip.todoticket.line', 'todoticket_id',
        string='Líneas de Detalle de Empleados')

    amount_total_bs = fields.Float(
        string='Monto Total (Bs)', compute='_compute_amount_totals',
        store=True, digits=(12, 2))

    amount_total_usd = fields.Float(
        string='Monto Equivalente ($ USD)', compute='_compute_amount_totals',
        store=True, digits=(12, 2))

    # Mantener amount_total para compatibilidad retroactiva
    amount_total = fields.Float(
        string='Monto Total en Bolívares (Bs)', compute='_compute_amount_totals',
        store=True, digits=(12, 2))

    total_records = fields.Integer(
        string='Total Empleados', compute='_compute_amount_totals', store=True)

    txt_filename = fields.Char('Nombre del Archivo TXT', size=256, readonly=True)
    txt_file = fields.Binary('Archivo TXT TodoTicket', readonly=True)

    @api.depends('line_ids', 'line_ids.amount_bs', 'tasa_bcv')
    def _compute_amount_totals(self):
        for rec in self:
            total_bs = sum(line.amount_bs for line in rec.line_ids)
            rec.amount_total_bs = round(total_bs, 2)
            rec.amount_total = round(total_bs, 2)
            rec.total_records = len(rec.line_ids)
            rate = rec.tasa_bcv or rec.env.company.get_bcv_rate() or 1.0
            if rate > 0:
                rec.amount_total_usd = round(total_bs / rate, 2)
            else:
                rec.amount_total_usd = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.payslip.todoticket') or _('Nuevo')
        return super(HrPayslipTodoticket, self).create(vals_list)

    def load_payslips(self):
        """Cargar nóminas desde los lotes seleccionados."""
        self.ensure_one()
        if not self.payslip_run_ids:
            raise UserError(_('Debe seleccionar al menos un lote de nómina.'))

        # Limpiar líneas previas y archivo previo
        self.line_ids.unlink()
        self.txt_filename = False
        self.txt_file = False

        line_vals = []
        for run in self.payslip_run_ids:
            for slip in run.slip_ids.filtered(lambda s: s.state in ('draft', 'verify', 'done', 'paid')):
                employee = slip.employee_id
                nationality = getattr(employee, 'nationality', 'V') or 'V'
                identification = employee.identification_id or ''
                # Limpiar cedula: solo digitos
                cedula_clean = ''.join(c for c in identification if c.isdigit())
                if not cedula_clean:
                    raise UserError(_('El empleado "%s" no tiene cédula de identidad configurada.') % employee.name)

                # Calcular monto en Bolívares del beneficio
                amount_bs = slip.net_wage_bs if hasattr(slip, 'net_wage_bs') and slip.net_wage_bs > 0 else (slip.total_bs if hasattr(slip, 'total_bs') else 0.0)

                line_vals.append({
                    'todoticket_id': self.id,
                    'payslip_id': slip.id,
                    'employee_id': employee.id,
                    'number': slip.name or slip.number or 'N/A',
                    'nationality': nationality if nationality in ('V', 'E') else 'V',
                    'identification_id': cedula_clean,
                    'employee_name': employee.name,
                    'amount_bs': amount_bs,
                    'tasa_bcv': self.tasa_bcv or self.env.company.get_bcv_rate(),
                })

        if not line_vals:
            raise UserError(_('No se encontraron recibos de nómina válidos en los lotes seleccionados.'))

        self.env['hr.payslip.todoticket.line'].create(line_vals)
        return True

    def generate_txt(self):
        """Generar archivo TXT formato oficial TodoTicket (41 posiciones por linea)."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Debe cargar las nóminas antes de generar el archivo TXT.'))
        if not self.company_code:
            raise UserError(_('Debe ingresar el código de la empresa asignado por TodoTicket.'))
        if not self.date_payment:
            raise UserError(_('Debe ingresar la fecha de abono.'))

        txt_lines = []
        for line in self.line_ids:
            if not line.identification_id:
                raise UserError(_('El empleado "%s" no tiene cédula de identidad.') % line.employee_name)

            # Nacionalidad: 1 caracter (V o E)
            nat = line.nationality if line.nationality in ('V', 'E') else 'V'

            # Cédula: 9 dígitos ceros a la izquierda
            cedula = line.identification_id.zfill(9)

            # Monto en céntimos en Bolívares: 21 dígitos ceros a la izquierda
            amount_centimos = int(round(line.amount_bs * 100))
            amount_str = str(amount_centimos).zfill(21)

            # Fecha de abono: ddmmyyyy (8 dígitos)
            date_str = self.date_payment.strftime('%d%m%Y')

            # Formato exacto TodoTicket: Nat(1) + Cedula(9) + "  "(2 espacios) + Monto(21) + Fecha(8) = 41 posiciones
            txt_lines.append('%s%s  %s%s' % (nat, cedula, amount_str, date_str))

        txt_content = '\r\n'.join(txt_lines) + '\r\n'

        now = datetime.now()
        self.txt_filename = 'Abo_tarjetas_%s_%s.txt' % (
            self.company_code,
            now.strftime('%d.%m.%y_%H.%M.%S'))
        self.txt_file = base64.b64encode(txt_content.encode('utf-8'))

    def action_done(self):
        if not self.txt_file:
            raise UserError(_('Debe generar el archivo TXT antes de marcarlo como Realizado.'))
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})


class HrPayslipTodoticketLine(models.Model):
    _name = 'hr.payslip.todoticket.line'
    _description = 'Línea de Detalle TXT TodoTicket'
    _order = 'id'

    todoticket_id = fields.Many2one(
        'hr.payslip.todoticket', string='Abono TodoTicket',
        required=True, ondelete='cascade')

    payslip_id = fields.Many2one('hr.payslip', string='Recibo de Nómina')
    employee_id = fields.Many2one('hr.employee', string='Empleado')

    number = fields.Char('N° Recibo')
    nationality = fields.Selection([('V', 'V'), ('E', 'E')], string='Nacionalidad', default='V')
    identification_id = fields.Char('Cédula')
    employee_name = fields.Char('Nombre Completo')

    tasa_bcv = fields.Float('Tasa BCV', digits=(12, 6), default=lambda self: self.env.company.get_bcv_rate())

    amount_bs = fields.Float('Monto a Abonar (Bs)', digits=(12, 2))
    amount_usd = fields.Float('Monto Equivalente ($ USD)', compute='_compute_amount_usd', store=True, digits=(12, 2))

    # Mantener 'amount' por alias
    amount = fields.Float('Monto en Bolívares (Bs)', related='amount_bs', readonly=False)

    @api.depends('amount_bs', 'tasa_bcv', 'todoticket_id.tasa_bcv')
    def _compute_amount_usd(self):
        for line in self:
            rate = line.tasa_bcv or (line.todoticket_id and line.todoticket_id.tasa_bcv) or line.env.company.get_bcv_rate() or 1.0
            if rate > 0 and line.amount_bs:
                line.amount_usd = round(line.amount_bs / rate, 2)
            else:
                line.amount_usd = 0.0
