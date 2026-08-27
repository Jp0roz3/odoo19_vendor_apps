# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo import fields


class TestFeedback9Validation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.l10n_ve_active = True
        cls.company.l10n_ve_retention_agent_municipal = True

        cls.currency_ves = cls.env['res.currency'].search([('name', 'in', ['VES', 'VEF', 'VEB'])], limit=1)
        if not cls.currency_ves:
            cls.currency_ves = cls.env.ref('base.USD')

        cls.state_ve = cls.env['res.country.state'].search([('country_id.code', '=', 'VE')], limit=1)
        if not cls.state_ve:
            cls.country_ve = cls.env['res.country'].search([('code', '=', 'VE')], limit=1) or cls.env.ref('base.ve')
            cls.state_ve = cls.env['res.country.state'].create({
                'name': 'Miranda Test',
                'code': 'MIR',
                'country_id': cls.country_ve.id,
            })

        cls.municipality = cls.env['l10n_ve.municipality'].create({
            'name': 'Municipio Chacao Test',
            'state_id': cls.state_ve.id,
            'wh_municipal_rate': 2.0,
        })

        cls.partner_agent = cls.env['res.partner'].create({
            'name': 'Cliente Agente Completo C.A.',
            'l10n_ve_rif': 'J-12345678-9',
            'l10n_ve_wh_iva_agent': True,
            'l10n_ve_wh_islr_agent': True,
            'l10n_ve_retention_agent_municipal': True,
            'l10n_ve_municipality_id': cls.municipality.id,
            'l10n_ve_municipal_activity': 'Servicios de TI',
            'l10n_ve_municipal_rate': 3.5,
        })

        cls.partner_normal = cls.env['res.partner'].create({
            'name': 'Cliente Normal S.A.',
            'l10n_ve_rif': 'J-98765432-1',
            'l10n_ve_wh_iva_agent': False,
            'l10n_ve_wh_islr_agent': False,
            'l10n_ve_retention_agent_municipal': False,
        })

        cls.product_service = cls.env['product.product'].create({
            'name': 'Servicio de Consultoria Test',
            'type': 'service',
            'list_price': 1000.0,
        })

        cls.product_goods = cls.env['product.product'].create({
            'name': 'Bien Tangible Test',
            'type': 'consu',
            'list_price': 500.0,
        })

    def test_07_partner_and_company_municipal_agent(self):
        self.assertTrue(hasattr(self.partner_agent, 'l10n_ve_retention_agent_municipal'))
        self.assertTrue(self.partner_agent.l10n_ve_retention_agent_municipal)
        self.assertFalse(self.partner_normal.l10n_ve_retention_agent_municipal)
        self.assertTrue(self.company.l10n_ve_retention_agent_municipal)

    def test_08_and_10_smart_buttons_and_service_detection(self):
        inv_agent = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_agent.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product_service.id,
                    'quantity': 1,
                    'price_unit': 1000.0,
                })
            ]
        })
        inv_agent._compute_l10n_ve_has_service_lines()
        inv_agent._compute_l10n_ve_wh_buttons_visibility()

        self.assertTrue(inv_agent.l10n_ve_has_service_lines)
        self.assertTrue(inv_agent.l10n_ve_show_wh_iva_button)
        self.assertTrue(inv_agent.l10n_ve_show_wh_islr_button)
        self.assertTrue(inv_agent.l10n_ve_show_wh_municipal_button)

        inv_normal = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_normal.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product_goods.id,
                    'quantity': 1,
                    'price_unit': 500.0,
                })
            ]
        })
        inv_normal._compute_l10n_ve_has_service_lines()
        inv_normal._compute_l10n_ve_wh_buttons_visibility()

        self.assertFalse(inv_normal.l10n_ve_has_service_lines)
        self.assertFalse(inv_normal.l10n_ve_show_wh_iva_button)
        self.assertFalse(inv_normal.l10n_ve_show_wh_islr_button)
        self.assertFalse(inv_normal.l10n_ve_show_wh_municipal_button)

    def test_09_municipal_territorial_synchronization(self):
        inv = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_agent.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product_service.id,
                    'quantity': 1,
                    'price_unit': 1000.0,
                })
            ]
        })

        wh_muni = self.env['account.wh.municipal'].new({
            'move_id': inv.id,
        })
        wh_muni._onchange_move_id()

        self.assertEqual(wh_muni.municipality_id, self.partner_agent.l10n_ve_municipality_id)
        self.assertEqual(wh_muni.economic_activity, self.partner_agent.l10n_ve_municipal_activity)
        self.assertEqual(wh_muni.rate_pct, self.partner_agent.l10n_ve_municipal_rate)

    def test_11_auto_reconcile_methods_exist(self):
        self.assertTrue(hasattr(self.env['account.wh.iva'], '_reconcile_withholding_with_invoice'))
        self.assertTrue(hasattr(self.env['account.wh.islr'], '_reconcile_withholding_with_invoice'))
        self.assertTrue(hasattr(self.env['account.wh.municipal'], '_reconcile_withholding_with_invoice'))

    def test_12_legal_taxes_exist_and_assigned(self):
        """Punto 12: Verificar catálogo de 14 impuestos oficiales SENIAT y configuración por defecto."""
        self.company._ensure_l10n_ve_chart_and_taxes()

        # 1. Verificar impuestos clave
        tax_sale_16 = self.env['account.tax'].search([
            ('name', '=', 'IVA 16% (Venta)'),
            ('company_id', '=', self.company.id)
        ], limit=1)
        self.assertTrue(tax_sale_16, "Debe existir IVA 16% (Venta)")
        self.assertEqual(tax_sale_16.amount, 16.0)

        tax_purch_16 = self.env['account.tax'].search([
            ('name', '=', 'IVA 16% (Compra)'),
            ('company_id', '=', self.company.id)
        ], limit=1)
        self.assertTrue(tax_purch_16, "Debe existir IVA 16% (Compra)")

        tax_igtf = self.env['account.tax'].search([
            ('name', '=', 'IGTF 3% (Venta)'),
            ('company_id', '=', self.company.id)
        ], limit=1)
        self.assertTrue(tax_igtf, "Debe existir IGTF 3% (Venta)")

        tax_no_sujeto = self.env['account.tax'].search([
            ('name', '=', 'No Sujeto a IVA (Venta)'),
            ('company_id', '=', self.company.id)
        ], limit=1)
        self.assertTrue(tax_no_sujeto, "Debe existir No Sujeto a IVA (Venta)")

        # 2. Verificar asignación de impuestos por defecto en la compañía
        self.assertEqual(self.company.account_sale_tax_id, tax_sale_16)
        self.assertEqual(self.company.account_purchase_tax_id, tax_purch_16)

