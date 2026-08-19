# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64, csv, io

class HrPayrollNoveltiesWizard(models.TransientModel):
    _name = 'hr.payroll.novelties.wizard'
    _description = 'Wizard de Carga Masiva de Variaciones / Novedades de Nómina'

    payslip_run_id = fields.Many2one('hr.payslip.run', string="Lote de Nómina Destino", required=True)
    csv_file = fields.Binary(string="Archivo CSV / Excel de Variaciones", help="Columnas: Cedula,TipoNovedad,HorasOMonto,Notas")
    file_name = fields.Char(string="Nombre del Archivo")

    line_ids = fields.One2many('hr.payroll.novelties.wizard.line', 'wizard_id', string="Líneas de Variaciones")

    def action_load_csv(self):
        self.ensure_one()
        if not self.csv_file:
            raise UserError(_("Por favor seleccione un archivo CSV antes de procesar."))

        content = base64.b64decode(self.csv_file).decode('utf-8-sig')
        reader = csv.reader(io.StringIO(content), delimiter=';')
        
        lines = []
        header = True
        for row in reader:
            if header:
                header = False
                continue
            if not row or len(row) < 3:
                continue

            cedula = row[0].strip()
            tipo = row[1].strip().lower()
            cantidad = float(row[2].strip().replace(',', '.')) if row[2] else 0.0
            nota = row[3].strip() if len(row) > 3 else ''

            emp = self.env['hr.employee'].search([('identification_id', '=', cedula)], limit=1)
            if not emp:
                emp = self.env['hr.employee'].search([('name', 'ilike', cedula)], limit=1)

            if emp:
                lines.append((0, 0, {
                    'employee_id': emp.id,
                    'novelty_type': tipo if tipo in ('he_diurna', 'he_nocturna', 'domingo', 'ausencia', 'bono') else 'he_diurna',
                    'quantity': cantidad,
                    'note': nota,
                }))

        self.write({'line_ids': [(5, 0, 0)] + lines})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payroll.novelties.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_apply_novelties(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No hay variaciones cargadas para aplicar."))

        cat_alw = self.env['hr.salary.rule.category'].search([('code', '=', 'ALW')], limit=1)
        cat_ded = self.env['hr.salary.rule.category'].search([('code', '=', 'DED')], limit=1)

        for line in self.line_ids:
            slip = self.env['hr.payslip'].search([
                ('payslip_run_id', '=', self.payslip_run_id.id),
                ('employee_id', '=', line.employee_id.id)
            ], limit=1)

            if not slip:
                continue

            wage_daily = slip.contract_id.wage_bs / 30.0 if slip.contract_id and slip.contract_id.wage_bs else 0.0
            wage_hourly = wage_daily / 8.0

            name = ''
            code = ''
            amount = 0.0
            category_id = cat_alw.id if cat_alw else False

            if line.novelty_type == 'he_diurna':
                name = f'Horas Extras Diurnas ({line.quantity} hrs)'
                code = 'HE_DIURNA'
                amount = round(line.quantity * wage_hourly * 1.5, 2)
            elif line.novelty_type == 'he_nocturna':
                name = f'Horas Extras Nocturnas ({line.quantity} hrs)'
                code = 'HE_NOCTURNA'
                amount = round(line.quantity * wage_hourly * 1.95, 2)
            elif line.novelty_type == 'domingo':
                name = f'Días Feriados / Domingos Trabajados ({line.quantity} días)'
                code = 'DOM_FERIADO'
                amount = round(line.quantity * wage_daily * 1.5, 2)
            elif line.novelty_type == 'ausencia':
                name = f'Descuento Ausencia No Justificada ({line.quantity} días)'
                code = 'DED_AUSENCIA'
                category_id = cat_ded.id if cat_ded else False
                amount = -abs(round(line.quantity * wage_daily, 2))
            elif line.novelty_type == 'bono':
                name = f'Bono Especial / Incentivo ({line.note or "Asignación"})'
                code = 'BONO_INCENTIVO'
                amount = round(line.quantity, 2)

            if category_id and amount != 0.0:
                self.env['hr.payslip.line'].create({
                    'slip_id': slip.id,
                    'name': name,
                    'code': code,
                    'category_id': category_id,
                    'sequence': 40,
                    'total': amount,
                })

        return {'type': 'ir.actions.act_window_close'}


class HrPayrollNoveltiesWizardLine(models.TransientModel):
    _name = 'hr.payroll.novelties.wizard.line'
    _description = 'Línea de Variaciones de Nómina'

    wizard_id = fields.Many2one('hr.payroll.novelties.wizard', string="Wizard", ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    novelty_type = fields.Selection([
        ('he_diurna', 'Horas Extras Diurnas (+50%)'),
        ('he_nocturna', 'Horas Extras Nocturnas (+95%)'),
        ('domingo', 'Domingos / Feriados Trabajados (+50%)'),
        ('ausencia', 'Deducción Ausencia No Justificada'),
        ('bono', 'Bono Especial / Incentivo Libre'),
    ], string="Tipo de Variación", default='he_diurna', required=True)

    quantity = fields.Float(string="Cantidad (Horas / Días / Monto Bs)", default=1.0, required=True)
    note = fields.Char(string="Justificación / Observación")
