from odoo import api, models
from datetime import datetime

class ReportZDetails(models.AbstractModel):
    _name = 'report.mai_pos_dual_currency_v19.report_z_details_template'
    _description = 'Lógica para el Reporte Z de Conciliación'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        z_reports = self.env['pos.fiscal.z.report'].search(domain, order='date asc, z_number asc')
        
        company = self.env.company
        
        # Calculate records data
        records = []
        for z in z_reports:
            alic_pct = 0.0
            if z.taxable_sales_bs > 0:
                alic_pct = (z.tax_amount_bs / z.taxable_sales_bs) * 100
                
            records.append({
                'date': z.date.strftime('%Y-%m-%d') if z.date else '',
                'z_number': z.z_number,
                'total_sales': z.total_sales_bs,
                'igtf': z.igtf_amount_bs,
                'exempt': z.exempt_sales_bs,
                'taxable': z.taxable_sales_bs,
                'alic_pct': round(alic_pct, 2)
            })

        return {
            'doc_ids': docids,
            'doc_model': 'pos.z.report.wizard',
            'date_from': date_from,
            'date_to': date_to,
            'company': company,
            'records': records,
        }
