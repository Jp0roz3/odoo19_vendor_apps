# -*- coding: utf-8 -*-
import base64
from odoo import models, fields, api

class BankPayrollExportWizard(models.TransientModel):
    _name = 'bank.payroll.export.wizard'
    _description = 'Wizard para Exportación de Disquetes Bancarios Masivos'

    payslip_run_id = fields.Many2one('hr.payslip.run', string="Lote de Nómina", required=True)
    bank_id = fields.Selection([
        ('banesco', 'Banesco (Format TXT 156 bytes)'),
        ('provincial', 'BBVA Provincial (Format TXT 120 bytes)'),
        ('bancaribe', 'BanCaribe (Asfalpro TXT Format)'),
        ('todoticket', 'Banesco / Todoticket (Cestaticket TXT/CSV)'),
        ('bdv', 'Banco de Venezuela (BDV TXT 120 bytes)'),
        ('mercantil', 'Banco Mercantil (Format CSV/TXT)'),
        ('bnc', 'Banco Nacional de Crédito (BNC TXT)'),
        ('bancamiga', 'Bancamiga (Format CSV)'),
    ], string="Banco Emisor", required=True, default='banesco')

    currency_id = fields.Selection([
        ('VES', 'Bolívares (VES)'),
        ('USD', 'Dólares ($ USD)'),
    ], string="Moneda del Pago", required=True, default='VES')

    payment_date = fields.Date(string="Fecha de Pago", default=fields.Date.today, required=True)
    file_data = fields.Binary(string="Archivo Bancario Generado", readonly=True)
    file_name = fields.Char(string="Nombre del Archivo")

    @api.model
    def default_get(self, fields_list):
        res = super(BankPayrollExportWizard, self).default_get(fields_list)
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        if active_model == 'hr.payslip.run' and active_id:
            res['payslip_run_id'] = active_id
        elif self.env.context.get('default_payslip_run_id'):
            res['payslip_run_id'] = self.env.context.get('default_payslip_run_id')
        return res

    def action_generate_bank_file(self):
        self.ensure_one()
        run = self.payslip_run_id
        lines = []

        for slip in run.slip_ids:
            net = slip.net_wage_bs if self.currency_id == 'VES' else slip.net_wage_usd
            employee_name = slip.employee_id.name or 'EMPLEADO'
            cedula = slip.employee_id.identification_id or 'V00000000'
            bank_accs = slip.employee_id.bank_account_ids
            acc = bank_accs[0].acc_number if bank_accs else '01140000000000000000'

            if self.bank_id == 'banesco':
                # Formato Banesco: Tipo(2) + Cuenta(20) + Monto(13) + Cedula(10) + Nombre(30)
                amount_str = f"{int(net * 100):013d}"
                line = f"01{acc[:20].ljust(20)}{amount_str}{cedula.ljust(10)}{employee_name[:30].ljust(30)}"
                lines.append(line)
            elif self.bank_id == 'provincial':
                # Formato BBVA Provincial: Tipo(1) + Cuenta(20) + Monto(15) + Cedula(10) + Nombre(40)
                amount_str = f"{int(net * 100):015d}"
                line = f"P{acc[:20].ljust(20)}{amount_str}{cedula.ljust(10)}{employee_name[:40].ljust(40)}"
                lines.append(line)
            elif self.bank_id == 'bancaribe':
                # Formato BanCaribe Asfalpro: RIF/Cedula(12) + Nombre(40) + Cuenta(20) + Monto(15) + Referencia(10)
                amount_str = f"{int(net * 100):015d}"
                ref = f"NOM{self.payment_date.strftime('%d%m%Y')}"
                line = f"{cedula.zfill(12)}{employee_name[:40].ljust(40)}{acc[:20].ljust(20)}{amount_str}{ref[:10].ljust(10)}"
                lines.append(line)
            elif self.bank_id == 'todoticket':
                # Formato Oficial TodoTicket Cestaticket (41 posiciones): Nat(1) + Cedula(9) + "  "(2) + MontoCéntimos(21) + Fecha(8 ddmmyyyy)
                nat = getattr(slip.employee_id, 'nationality', 'V') or 'V'
                nat = nat if nat in ('V', 'E') else 'V'
                ced_digits = ''.join(c for c in cedula if c.isdigit()).zfill(9)
                amount_str = f"{int(round(net * 100)):021d}"
                date_str = self.payment_date.strftime('%d%m%Y')
                line = f"{nat}{ced_digits}  {amount_str}{date_str}"
                lines.append(line)
            elif self.bank_id == 'bdv':
                # Formato BDV: Cuenta(20) + Monto(15) + Cedula(10) + Nombre(40)
                amount_str = f"{int(net * 100):015d}"
                line = f"{acc[:20].ljust(20)}{amount_str}{cedula.ljust(10)}{employee_name[:40].ljust(40)}"
                lines.append(line)
            else:
                # Formato Estándar CSV/TXT (Mercantil, BNC, Bancamiga)
                line = f"{cedula};{employee_name};{acc};{net:.2f};{self.currency_id};{self.payment_date}"
                lines.append(line)

        content = "\r\n".join(lines)
        file_b64 = base64.b64encode(content.encode('utf-8'))
        ext = 'txt' if self.bank_id in ['banesco', 'provincial', 'bancaribe', 'todoticket', 'bdv', 'bnc'] else 'csv'
        filename = f"PAYROLL_{self.bank_id.upper()}_{self.currency_id}_{self.payment_date.strftime('%Y%m%d')}.{ext}"

        self.write({
            'file_data': file_b64,
            'file_name': filename
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'bank.payroll.export.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
