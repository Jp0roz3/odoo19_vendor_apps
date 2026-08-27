# -*- coding: utf-8 -*-
"""
Venezuela360: post_init_hook
=============================
Se ejecuta al instalar el módulo.
Configura valores predeterminados seguros en la compañía activa
y genera automáticamente los registros de demostración E2E (Presupuestos, Facturas,
Retenciones, Pagos Duales Bimoneda y Diarios).

Autor: JeanPerozo / Nubelco
"""
import logging

_logger = logging.getLogger(__name__)


def _ensure_spanish_langs(env):
    """
    Activa los idiomas 'es' (Español) y 'es_VE' (Español Venezuela) en la BD.
    Esto garantiza que el router de Odoo 19 resuelva sin 500 cualquier request
    de navegador con Accept-Language: es-419, es-ES o es.

    Estrategia:
      1. Activar el registro base.lang_es (Spanish) via res.lang
      2. Activar el registro base.lang_es_VE (Spanish (Venezuela)) via res.lang
      3. Como fallback, insertar/actualizar directamente via SQL si el ORM falla.
    """
    for lang_code in ('es', 'es_VE'):
        try:
            lang = env['res.lang'].with_context(active_test=False).search(
                [('code', '=', lang_code)], limit=1
            )
            if lang and not lang.active:
                lang.write({'active': True})
                _logger.info('Venezuela360: Idioma %s activado.', lang_code)
            elif not lang:
                # Try loading the language pack
                try:
                    env['res.lang']._activate_lang(lang_code)
                    _logger.info('Venezuela360: Idioma %s cargado e instalado.', lang_code)
                except Exception as ex:
                    _logger.warning('Venezuela360: No se pudo cargar %s: %s', lang_code, ex)
            else:
                _logger.info('Venezuela360: Idioma %s ya estaba activo.', lang_code)
        except Exception as e:
            _logger.warning('Venezuela360: Error al activar idioma %s: %s', lang_code, e)

    # Fallback SQL - asegurar que url_code='es' para es_VE (routing directo sin prefijo)
    try:
        env.cr.execute("""
            UPDATE res_lang 
            SET url_code = 'es_VE'
            WHERE code = 'es_VE' AND (url_code IS NULL OR url_code != 'es_VE');
        """)
    except Exception as e:
        _logger.warning('Venezuela360: Error actualizando url_code para es_VE: %s', e)


def post_init_hook(env):
    """
    Hook de post-instalación de Venezuela360.
    - Activa idiomas es y es_VE en la base de datos para resolver todos los
      navegadores en español sin excepción 500.
    - Asigna las secuencias de retención a la compañía activa si aún no las tiene.
    - Genera automáticamente datos de demostración E2E.
    """
    company = env.company

    try:
        # ─── PASO 1: Activar idiomas es y es_VE en res_lang ─────────────────
        # Sin esto, cualquier petición con Accept-Language: es-419 o es-ES
        # arroja Internal Server Error 500 en la ruta raíz /odoo de Odoo 19.
        _ensure_spanish_langs(env)
    except Exception as e:
        _logger.warning('Venezuela360 post_init_hook: Error al activar idiomas: %s', str(e))

    try:
        # Asignar secuencia de retención IVA
        if not company.l10n_ve_wh_iva_sequence_id:
            seq_iva = env.ref('l10n_ve_full.seq_wh_iva', raise_if_not_found=False)
            if seq_iva:
                company.l10n_ve_wh_iva_sequence_id = seq_iva

        # Asignar secuencia de retención ISLR
        if not company.l10n_ve_wh_islr_sequence_id:
            seq_islr = env.ref('l10n_ve_full.seq_wh_islr', raise_if_not_found=False)
            if seq_islr:
                company.l10n_ve_wh_islr_sequence_id = seq_islr

        # Asignar secuencia de retención Municipal
        if not company.l10n_ve_wh_municipal_sequence_id:
            seq_mun = env.ref('l10n_ve_full.seq_wh_municipal', raise_if_not_found=False)
            if seq_mun:
                company.l10n_ve_wh_municipal_sequence_id = seq_mun

        # Garantizar grupos de impuestos, cuentas fiscales VEN-NIF y catálogo oficial SENIAT
        company._ensure_l10n_ve_chart_and_taxes()

        _logger.info('Venezuela360: Impuestos y cuentas fiscales configurados para %s.', company.name)

        # Generar Registros E2E para Pruebas del Usuario
        _create_e2e_demo_data(env, company)

    except Exception as e:
        _logger.warning('Venezuela360 post_init_hook: Error no crítico: %s', str(e))


def _create_e2e_demo_data(env, company):
    _logger.info('Venezuela360: Generando datos de prueba E2E (Presupuestos, Facturas, Retenciones y Pagos)...')
    try:
        # Tasa BCV (777.4161)
        rate_obj = env['l10n_ve.exchange.rate']
        if not rate_obj.search([('date', '=', '2026-08-20')]):
            rate_obj.create({'date': '2026-08-20', 'rate': 777.4161, 'company_id': company.id})

        # Monedas
        usd = env['res.currency'].search([('name', '=', 'USD')], limit=1)
        ves = env['res.currency'].search([('name', 'in', ['VES', 'VEF', 'VEB'])], limit=1)
        if not usd or not ves:
            _logger.warning('Venezuela360 post_init_hook: Monedas USD/VES no encontradas.')
            return

        # Diarios de Banco
        bank_usd = env['account.journal'].search([('type', '=', 'bank'), ('currency_id', '=', usd.id)], limit=1)
        if not bank_usd:
            bank_usd = env['account.journal'].create({
                'name': 'Banco Nacional Dólares (USD)',
                'code': 'BUSD',
                'type': 'bank',
                'currency_id': usd.id,
                'company_id': company.id,
            })

        bank_ves = env['account.journal'].search([('type', '=', 'bank'), ('currency_id', '=', False)], limit=1)
        if not bank_ves:
            bank_ves = env['account.journal'].create({
                'name': 'Banco Mercantil Bolívares (VES)',
                'code': 'BVES',
                'type': 'bank',
                'company_id': company.id,
            })

        # Partners
        partner_obj = env['res.partner']
        customer = partner_obj.search([('name', '=', 'Corporación KAIROS Enterprise C.A.')], limit=1)
        if not customer:
            customer = partner_obj.create({
                'name': 'Corporación KAIROS Enterprise C.A.',
                'l10n_ve_rif': 'J-123456789',
                'is_company': True,
            })

        vendor = partner_obj.search([('name', '=', 'Proveedor Servisuministros C.A.')], limit=1)
        if not vendor:
            vendor = partner_obj.create({
                'name': 'Proveedor Servisuministros C.A.',
                'l10n_ve_rif': 'J-987654321',
                'is_company': True,
            })

        # Impuestos
        tax_sale = env['account.tax'].search([('type_tax_use', '=', 'sale'), ('amount', '=', 16.0)], limit=1)
        tax_purch = env['account.tax'].search([('type_tax_use', '=', 'purchase'), ('amount', '=', 16.0)], limit=1)

        # Presupuestos de Venta (Sale Order)
        if 'sale.order' in env:
            so1 = env['sale.order'].search([('partner_id', '=', customer.id), ('note', '=', 'Demo SO #1')], limit=1)
            if not so1:
                so1 = env['sale.order'].create({
                    'partner_id': customer.id,
                    'currency_id': usd.id,
                    'note': 'Demo SO #1',
                    'order_line': [(0, 0, {
                        'name': 'Servicio de Consultoría de Software ERP Odoo 19',
                        'product_uom_qty': 1,
                        'price_unit': 1000.0,
                        'tax_id': [(6, 0, tax_sale.ids)] if tax_sale else [],
                    })]
                })
                so1.action_confirm()

            so2 = env['sale.order'].search([('partner_id', '=', customer.id), ('note', '=', 'Demo SO #2')], limit=1)
            if not so2:
                so2 = env['sale.order'].create({
                    'partner_id': customer.id,
                    'currency_id': usd.id,
                    'note': 'Demo SO #2',
                    'order_line': [(0, 0, {
                        'name': 'Licencias de Software Anual Odoo 19',
                        'product_uom_qty': 1,
                        'price_unit': 500.0,
                        'tax_id': [(6, 0, tax_sale.ids)] if tax_sale else [],
                    })]
                })
                so2.action_confirm()

        # Facturas de Venta (out_invoice)
        move_obj = env['account.move']
        inv1 = move_obj.search([('partner_id', '=', customer.id), ('l10n_ve_control_number', '=', '00-00100200')], limit=1)
        if not inv1:
            inv1 = move_obj.create({
                'move_type': 'out_invoice',
                'partner_id': customer.id,
                'currency_id': usd.id,
                'invoice_date': '2026-08-20',
                'l10n_ve_control_number': '00-00100200',
                'invoice_line_ids': [(0, 0, {
                    'name': 'Servicio de Consultoría de Software ERP Odoo 19',
                    'quantity': 1,
                    'price_unit': 1000.0,
                    'tax_ids': [(6, 0, tax_sale.ids)] if tax_sale else [],
                })]
            })
            inv1.action_post()

            # Retención IVA
            if 'account.wh.iva' in env:
                wh1 = env['account.wh.iva'].create({
                    'wh_type': 'customer',
                    'move_id': inv1.id,
                    'partner_id': customer.id,
                    'date': '2026-08-20',
                    'wh_rate': 75.0,
                })
                wh1.action_confirm()

            # Pago en USD
            pay1 = env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': customer.id,
                'amount': 1040.0,
                'currency_id': usd.id,
                'journal_id': bank_usd.id,
                'date': '2026-08-20',
                'ref': f'Pago Factura {inv1.name} en USD',
            })
            pay1.action_post()

        inv2 = move_obj.search([('partner_id', '=', customer.id), ('l10n_ve_control_number', '=', '00-00100201')], limit=1)
        if not inv2:
            inv2 = move_obj.create({
                'move_type': 'out_invoice',
                'partner_id': customer.id,
                'currency_id': usd.id,
                'invoice_date': '2026-08-20',
                'l10n_ve_control_number': '00-00100201',
                'invoice_line_ids': [(0, 0, {
                    'name': 'Licencias de Software Anual Odoo 19',
                    'quantity': 1,
                    'price_unit': 500.0,
                    'tax_ids': [(6, 0, tax_sale.ids)] if tax_sale else [],
                })]
            })
            inv2.action_post()

            # Pago en VES
            pay2 = env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': customer.id,
                'amount': inv2.l10n_ve_amount_total_bs,
                'currency_id': ves.id,
                'journal_id': bank_ves.id,
                'date': '2026-08-20',
                'ref': f'Pago Factura {inv2.name} en Bolívares Bs.',
            })
            pay2.action_post()

        # Factura de Compra (in_invoice)
        inv_p1 = move_obj.search([('partner_id', '=', vendor.id), ('l10n_ve_control_number', '=', '00-00300400')], limit=1)
        if not inv_p1:
            inv_p1 = move_obj.create({
                'move_type': 'in_invoice',
                'partner_id': vendor.id,
                'currency_id': usd.id,
                'invoice_date': '2026-08-20',
                'l10n_ve_control_number': '00-00300400',
                'invoice_line_ids': [(0, 0, {
                    'name': 'Servidores de Infraestructura Cloud Dedicada',
                    'quantity': 1,
                    'price_unit': 600.0,
                    'tax_ids': [(6, 0, tax_purch.ids)] if tax_purch else [],
                })]
            })
            inv_p1.action_post()

            # Retención IVA Proveedor
            if 'account.wh.iva' in env:
                wh_p1 = env['account.wh.iva'].create({
                    'wh_type': 'supplier',
                    'move_id': inv_p1.id,
                    'partner_id': vendor.id,
                    'date': '2026-08-20',
                    'wh_rate': 75.0,
                })
                wh_p1.action_confirm()

            # Pago Proveedor en USD
            pay_p1 = env['account.payment'].create({
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': vendor.id,
                'amount': 624.0,
                'currency_id': usd.id,
                'journal_id': bank_usd.id,
                'date': '2026-08-20',
                'ref': f'Pago Proveedor Factura {inv_p1.name} en USD',
            })
            pay_p1.action_post()

        _logger.info('✅ Venezuela360: Registros de prueba E2E creados con éxito.')
    except Exception as e:
        _logger.warning('Venezuela360 post_init_hook _create_e2e_demo_data: Error no crítico: %s', str(e))
