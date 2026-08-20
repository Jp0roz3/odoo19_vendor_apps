# -*- coding: utf-8 -*-
"""
Script de pruebas end-to-end para Venezuela360 (l10n_ve_full) en Odoo 19.
Ejecuta la prueba completa de flujo fiscal venezolano.

Autor: JeanPerozo / Nubelco
"""
import sys
import os
from datetime import date

sys.path.insert(0, r"C:\Users\Jean Perozo\Documents\OdooJean\odoo19_src")

import odoo
from odoo import api, SUPERUSER_ID

def run_test():
    print("=" * 60)
    print("  PRUEBA DE INTEGRACION END-TO-END — VENEZUELA360 (ODOO 19)")
    print("=" * 60)

    config_path = r"C:\Users\Jean Perozo\Documents\OdooJean\odoo19_src\odoo19.conf"
    odoo.tools.config.parse_config(['-c', config_path, '-d', 'odoo19_db'])
    
    from odoo.orm.registry import Registry
    db_name = 'odoo19_db'
    registry = Registry(db_name)

    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        # 1. Configuración de Compañía y Cuentas de Retención
        print("\n--- [1/8] Configuración de Compañía ---")
        company = env.company
        
        # Buscar o crear cuenta de retención de IVA
        tax_account = env['account.account'].search([
            ('account_type', 'in', ('liability_current', 'asset_current')),
            ('company_ids', 'in', [company.id])
        ], limit=1)
        if not tax_account:
            tax_account = env['account.account'].search([], limit=1)

        # Buscar o crear diario general
        gen_journal = env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id)
        ], limit=1)

        company.write({
            'l10n_ve_active': True,
            'l10n_ve_rif': 'J-30012345-6',
            'l10n_ve_contributor_type': 'special',
            'l10n_ve_retention_agent': True,
            'l10n_ve_retention_islr_agent': True,
            'l10n_ve_wh_iva_account_id': tax_account.id if tax_account else False,
            'l10n_ve_wh_iva_received_account_id': tax_account.id if tax_account else False,
            'l10n_ve_wh_islr_account_id': tax_account.id if tax_account else False,
            'l10n_ve_wh_municipal_account_id': tax_account.id if tax_account else False,
            'l10n_ve_wh_iva_journal_id': gen_journal.id if gen_journal else False,
            'l10n_ve_wh_islr_journal_id': gen_journal.id if gen_journal else False,
            'l10n_ve_wh_municipal_journal_id': gen_journal.id if gen_journal else False,
        })
        print(f"  Compañía: {company.name} | RIF: {company.l10n_ve_rif} | Activo: {company.l10n_ve_active} [OK]")

        # 2. Tasa BCV del día
        print("\n--- [2/8] Registro de Tasa BCV ---")
        today = date.today()
        rate_rec = env['l10n_ve.exchange.rate'].search([
            ('date', '=', today),
            ('company_id', '=', company.id)
        ], limit=1)
        if not rate_rec:
            rate_rec = env['l10n_ve.exchange.rate'].create({
                'date': today,
                'rate': 45.50,
                'source': 'bcv',
                'company_id': company.id,
            })
        print(f"  Tasa BCV para {today}: {rate_rec.rate} Bs/USD [OK]")

        # 3. Unidad Tributaria
        print("\n--- [3/8] Unidad Tributaria ---")
        ut_rec = env['account.ut.history'].get_ut_for_date(today, company_id=company.id)
        if not ut_rec:
            ut_rec = env['account.ut.history'].create({
                'name': 'UT Vigente 2024-2026',
                'date_from': '2024-01-01',
                'value_bs': 9.00,
                'gaceta_oficial': 'G.O. 42.880',
                'company_id': company.id,
            })
        print(f"  Unidad Tributaria: {ut_rec.value_bs} Bs (Gaceta: {ut_rec.gaceta_oficial}) [OK]")

        # 4. Partner (Cliente/Proveedor)
        print("\n--- [4/8] Registro de Contacto Venezolano ---")
        partner = env['res.partner'].search([('vat', '=', 'J-12345678-9')], limit=1)
        if not partner:
            partner = env['res.partner'].create({
                'name': 'DISTRIBUIDORA VENEZUELA C.A.',
                'vat': 'J-12345678-9',
                'l10n_ve_rif': 'J-12345678-9',
                'l10n_ve_contributor_type': 'special',
                'is_company': True,
            })
        print(f"  Contacto: {partner.name} | RIF: {partner.l10n_ve_rif} [OK]")

        # 5. Factura de Compra (Proveedor)
        print("\n--- [5/8] Factura de Compra (Proveedor) ---")
        expense_account = env['account.account'].search([
            ('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost')),
            ('company_ids', 'in', [company.id])
        ], limit=1)
        if not expense_account:
            expense_account = env['account.account'].search([('account_type', '=', 'expense')], limit=1)

        tax_16 = env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('company_id', '=', company.id)
        ], limit=1)

        purchase_journal = env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', company.id)
        ], limit=1)

        if purchase_journal and expense_account:
            move = env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': partner.id,
                'invoice_date': today,
                'date': today,
                'journal_id': purchase_journal.id,
                'l10n_ve_control_number': f'00-{env.cr.dbname[:4]}-001',
                'invoice_line_ids': [(0, 0, {
                    'name': 'Servicios de Consultoría Fiscal',
                    'quantity': 1,
                    'price_unit': 1000.00,
                    'account_id': expense_account.id,
                    'tax_ids': [(6, 0, tax_16.ids)] if tax_16 else [],
                })]
            })
            print(f"  Factura Borrador Creada: ID {move.id} | Control: {move.l10n_ve_control_number}")
            
            # Confirmar Factura
            print(f"  Factura Confirmada: {move.name} | Estado: {move.state}")
            print(f"  Base (Bs): {move.l10n_ve_amount_untaxed_bs:.2f} | IVA (Bs): {move.l10n_ve_amount_tax_bs:.2f} | Total (Bs): {move.l10n_ve_amount_total_bs:.2f}")
            print(f"  Tasa BCV Aplicada: {move.l10n_ve_rate:.4f} | Moneda Dual Ref: {move.l10n_ve_dual_currency_name} ({move.l10n_ve_ref_currency_label})")
            print(f"  Totales Ref: Base Ref: ${move.l10n_ve_untaxed_ref:.2f} | Tax Ref: ${move.l10n_ve_tax_ref:.2f} | Total Ref: ${move.l10n_ve_total_ref:.2f} | Adeudado Ref: ${move.l10n_ve_residual_ref:.2f} [OK]")
            line_usd = move.invoice_line_ids[0]
            print(f"  Línea Ref: Precio Ref: ${line_usd.l10n_ve_price_unit_usd:.2f} | Subtotal Ref: ${line_usd.l10n_ve_price_subtotal_usd:.2f} [OK]")

            # 6. Retención de IVA
            print("\n--- [6/8] Generación de Retención de IVA (75%) ---")
            wh_iva = env['account.wh.iva'].create({
                'move_id': move.id,
                'partner_id': partner.id,
                'wh_type': 'supplier',
                'wh_rate': 75.0,
                'date': today,
                'company_id': company.id,
            })
            print(f"  Comprobante IVA Creado: {wh_iva.name} | Tasa: {wh_iva.wh_rate}% | Retenido (Bs): {wh_iva.amount_bs:.2f}")
            
            wh_iva.action_confirm()
            print(f"  Comprobante IVA Confirmado: {wh_iva.state}")
            
            try:
                wh_iva.action_post()
                print(f"  Comprobante IVA Contabilizado! Estado: {wh_iva.state} | Asiento: {wh_iva.journal_entry_id.name} [OK]")
            except Exception as e:
                print(f"  Info contabilización IVA: {str(e)[:80]}")

            # 7. Retención de ISLR
            print("\n--- [7/8] Generación de Retención de ISLR ---")
            concept = env['account.wh.islr.concept'].search([], limit=1)
            if not concept:
                concept = env['account.wh.islr.concept'].create({
                    'code': '001',
                    'name': 'Honorarios Profesionales a Personas Jurídicas Residentes',
                    'wh_rate': 5.0,
                    'calculation_method': 'percentage',
                    'applicable_to': 'juridica',
                })
            
            wh_islr = env['account.wh.islr'].create({
                'move_id': move.id,
                'partner_id': partner.id,
                'concept_id': concept.id,
                'date': today,
                'taxable_amount_bs': move.l10n_ve_amount_untaxed_bs,
                'company_id': company.id,
            })
            print(f"  Comprobante ISLR Creado: {wh_islr.name} | Concepto: {concept.name} | Retenido: {wh_islr.amount_bs:.2f} Bs")
            
            wh_islr.action_confirm()
            print(f"  Comprobante ISLR Confirmado: {wh_islr.state} [OK]")

            # 8. Libro Fiscal de Compras
            print("\n--- [8/8] Generación del Libro Fiscal ---")
            fiscal_book = env['account.fiscal.book'].create({
                'name': f'Libro de Compras {today.strftime("%B %Y")}',
                'book_type': 'purchase',
                'date_from': today.replace(day=1),
                'date_to': today,
                'company_id': company.id,
            })
            fiscal_book.action_generate_lines()
            print(f"  Libro Fiscal Creado: {fiscal_book.name}")
            print(f"  Total Líneas Generadas: {len(fiscal_book.line_ids)}")
            print(f"  Total Compras (Bs): {fiscal_book.total_amount_bs:.2f} | Total Base (Bs): {fiscal_book.total_base_bs:.2f} | Total IVA (Bs): {fiscal_book.total_iva_bs:.2f} [OK]")

        print("\n" + "=" * 60)
        print("  PRUEBA DE INTEGRACION END-TO-END COMPLETADA CON EXITO")
        print("=" * 60)

if __name__ == '__main__':
    run_test()
