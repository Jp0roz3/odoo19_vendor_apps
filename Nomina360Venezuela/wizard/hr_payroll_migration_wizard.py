# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64, csv, io
from datetime import datetime

class HrPayrollMigrationWizard(models.TransientModel):
    _name = 'hr.payroll.migration.wizard'
    _description = 'Wizard de Migración de Datos Maestros, Salarios Históricos y Prestaciones Acumuladas'

    company_id = fields.Many2one('res.company', string="Compañía Destino", default=lambda self: self.env.company, required=True)

    csv_file_employees = fields.Binary(string="Archivo CSV de Empleados y Contratos", help="Columnas: Cedula,Nombre,Email,Cargo,FechaIngreso,SalarioUSD,SalarioBs,Frecuencia")
    file_name_emp = fields.Char(string="Nombre Archivo Empleados")

    csv_file_prestaciones = fields.Binary(string="Archivo CSV de Saldos Acumulados de Prestaciones", help="Columnas: Cedula,Año,Trimestre,SalarioIntegralBs,DiasGarantia,DiasAdicionales,AcumuladoGarantiaBs,InteresesBs")
    file_name_prest = fields.Char(string="Nombre Archivo Prestaciones")

    imported_employees_count = fields.Integer(string="Empleados / Contratos Importados", default=0, readonly=True)
    imported_prestaciones_count = fields.Integer(string="Registros de Prestaciones Importados", default=0, readonly=True)

    def action_import_data(self):
        self.ensure_one()
        emp_count = 0
        prest_count = 0

        # 1. Import Employees & Contracts
        if self.csv_file_employees:
            content = base64.b64decode(self.csv_file_employees).decode('utf-8-sig')
            reader = csv.reader(io.StringIO(content), delimiter=';')
            header = True
            for row in reader:
                if header:
                    header = False
                    continue
                if not row or len(row) < 5:
                    continue

                cedula = row[0].strip()
                nombre = row[1].strip()
                email = row[2].strip() if len(row) > 2 else ''
                cargo = row[3].strip() if len(row) > 3 else 'Empleado'
                f_ing_str = row[4].strip() if len(row) > 4 else '01/01/2024'
                sal_usd = float(row[5].strip().replace(',', '.')) if len(row) > 5 and row[5] else 0.0
                sal_bs = float(row[6].strip().replace(',', '.')) if len(row) > 6 and row[6] else 0.0
                frec = row[7].strip().lower() if len(row) > 7 else 'quincenal'

                try:
                    f_ing = datetime.strptime(f_ing_str, '%d/%m/%Y').date()
                except Exception:
                    f_ing = fields.Date.today()

                emp = self.env['hr.employee'].search([('identification_id', '=', cedula)], limit=1)
                if not emp:
                    emp = self.env['hr.employee'].create({
                        'name': nombre,
                        'identification_id': cedula,
                        'work_email': email,
                        'job_title': cargo,
                        'company_id': self.company_id.id,
                    })

                contract = self.env['hr.contract'].search([('employee_id', '=', emp.id)], limit=1)
                if not contract:
                    self.env['hr.contract'].create({
                        'name': f'Contrato Migrado - {nombre}',
                        'employee_id': emp.id,
                        'company_id': self.company_id.id,
                        'date_start': f_ing,
                        'wage_usd': sal_usd,
                        'wage_bs': sal_bs or (sal_usd * 757.74),
                        'wage': sal_bs or (sal_usd * 757.74),
                        'wage_currency_type': 'usd' if sal_usd > 0 else 'bs',
                        'schedule_pay': frec if frec in ('semanal', 'quincenal', 'especial') else 'quincenal',
                        'state': 'open',
                    })
                emp_count += 1

        # 2. Import Prestaciones Social Accumulations
        if self.csv_file_prestaciones:
            content = base64.b64decode(self.csv_file_prestaciones).decode('utf-8-sig')
            reader = csv.reader(io.StringIO(content), delimiter=';')
            header = True
            for row in reader:
                if header:
                    header = False
                    continue
                if not row or len(row) < 5:
                    continue

                cedula = row[0].strip()
                ano = int(row[1].strip())
                trim = row[2].strip()
                sal_int_bs = float(row[3].strip().replace(',', '.'))
                dias_gar = int(row[4].strip())
                dias_adic = int(row[5].strip()) if len(row) > 5 and row[5] else 0
                acum_gar = float(row[6].strip().replace(',', '.')) if len(row) > 6 and row[6] else (sal_int_bs * (dias_gar + dias_adic))
                acum_int = float(row[7].strip().replace(',', '.')) if len(row) > 7 and row[7] else 0.0

                emp = self.env['hr.employee'].search([('identification_id', '=', cedula)], limit=1)
                if not emp or not emp.contract_id:
                    continue

                exist = self.env['hr.prestaciones.line'].search([
                    ('employee_id', '=', emp.id),
                    ('year', '=', ano),
                    ('quarter', '=', trim)
                ], limit=1)

                if not exist:
                    self.env['hr.prestaciones.line'].create({
                        'employee_id': emp.id,
                        'contract_id': emp.contract_id.id,
                        'company_id': self.company_id.id,
                        'year': ano,
                        'quarter': trim if trim in ('1', '2', '3', '4') else '1',
                        'salario_integral_bs': sal_int_bs,
                        'dias_garantia': dias_gar,
                        'dias_adicionales': dias_adic,
                        'monto_garantia_acumulada_bs': acum_gar,
                        'intereses_acumulados_bs': acum_int,
                    })
                prest_count += 1

        self.write({
            'imported_employees_count': emp_count,
            'imported_prestaciones_count': prest_count,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payroll.migration.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
