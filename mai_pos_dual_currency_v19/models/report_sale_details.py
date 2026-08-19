# -*- coding: utf-8 -*-
from odoo import api, fields, models

class ReportSaleDetails(models.AbstractModel):
    _inherit = 'report.point_of_sale.report_saledetails'

    @api.model
    def get_sale_details(self, date_start=False, date_stop=False, config_ids=False, session_ids=False):
        # Llamamos al método original para obtener toda la data
        res = super(ReportSaleDetails, self).get_sale_details(date_start, date_stop, config_ids, session_ids)
        
        # Obtenemos la configuración del POS para extraer la tasa y si la moneda dual está activa
        configs = self.env['pos.config'].browse(config_ids) if config_ids else self.env['pos.config']
        if not configs and session_ids:
            sessions = self.env['pos.session'].browse(session_ids)
            configs = sessions.mapped('config_id')
            
        if configs:
            config = configs[0]
            res['show_dual_currency'] = config.show_dual_currency
            res['rate_company'] = config.show_currency_rate
            
            # Determinamos cuál es la moneda principal
            is_main_usd = config.currency_id.name == 'USD'
            res['is_main_usd'] = is_main_usd
            res['main_symbol'] = '$' if is_main_usd else 'Bs.F'
            res['sec_symbol'] = 'Bs.F' if is_main_usd else '$'
        else:
            res['show_dual_currency'] = False
            res['rate_company'] = 1.0
            res['is_main_usd'] = True
            res['main_symbol'] = '$'
            res['sec_symbol'] = 'Bs.F'
            
        return res
