# -*- coding: utf-8 -*-
{
    'name': 'Venezuela360: Localización Completa',
    'version': '19.0.2.1.0',
    'category': 'Accounting/Localizations',
    'summary': (
        'Localización fiscal, contable y tributaria completa para Venezuela: '
        'retenciones IVA/ISLR/Municipal, reportes SENIAT (TXT IVA, XML ISLR, ARCV, Patente), '
        'libros fiscales, Unidad Tributaria histórica, territorialidad, '
        'doble moneda BS/USD con tasa BCV / Personalizada / Comercial.'
    ),
    'description': """
Venezuela360: Localización Completa
=====================================
Módulo de localización venezolana integral para Odoo 19 Enterprise y Community.

Funcionalidades principales:
-----------------------------
- 💱 **Tasa BCV y Multi-Tasa**: Tasa Oficial BCV, Tasa Personalizada y Acuerdo Comercial en Facturas y Asientos con cálculo dual.
- 💰 **Contabilidad Dual BS/USD**: Facturas, asientos, pagos y reportes con equivalencia y totales en moneda referencial.
- 🧾 **Retención de IVA**: Cálculo automático (75% / 100%), comprobante PDF y generador de archivo TXT reglamentario SENIAT de 14 campos.
- 📊 **Retención de ISLR**: Por concepto/tabla SENIAT, comprobante PDF y generador de archivo XML oficial SENIAT v1.0.
- 📜 **Reporte AR-CV**: Comprobante anual acumulado de retenciones de ISLR para beneficiarios.
- 🏛️ **Patente Municipal (IAE)**: Retenciones por clasificador de actividad económica municipal y reporte para alcaldías.
- 📑 **Factura Forma Libre**: Formato legal pre-impreso y digital con número de control, datos de imprenta y desglose dual.
- 🔴 **Notas de Débito**: Emisión directa de notas de débito de cliente y proveedor.
- 📚 **Libros Fiscales e Inventario**: Libros de compras, ventas y libro de inventario y balances valorado.
- 📈 **Diferencial Cambiario**: Reporte de ganancia/pérdida cambiaria en inventario y ventas.
- 🔢 **Talonarios y Control Fiscal**: Gestión de secuencias de control (00-XXXXXXXX) y datos de imprenta autorizada.
- 🗺️ **Territorialidad Venezolana**: 24 estados, municipios y parroquias.

Autor: JeanPerozo / Nubelco
    """,
    'author': 'JeanPerozo / Nubelco',
    'website': 'https://www.nubelco.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'mail',
        'product',
        'sale',
        'purchase',
        'stock',
    ],
    'data': [
        # Seguridad
        'security/ir_groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rules.xml',

        # Datos iniciales
        'data/sequence_data.xml',
        'data/territory_state_data.xml',
        'data/account_tax_group_data.xml',
        'data/account_tax_data.xml',
        'data/ut_history_data.xml',

        # Vistas: configuración
        'views/res_config_settings_views.xml',

        # Vistas: tasa BCV y control
        'views/exchange_rate_views.xml',
        'views/control_number_views.xml',

        # Vistas: Unidad Tributaria
        'views/ut_history_views.xml',

        # Vistas: territorialidad
        'views/territory_views.xml',

        # Vistas: contactos y productos
        'views/res_partner_views.xml',
        'views/product_views.xml',

        # Vistas: documentos contables
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/account_tax_views.xml',
        'views/account_journal_dashboard_views.xml',
        'views/account_bank_statement_views.xml',
        'views/account_report_bimoneda_views.xml',

        # Vistas: ventas, compras y almacén
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',

        # Vistas: retenciones
        'views/withholding_iva_views.xml',
        'views/withholding_islr_views.xml',
        'views/withholding_municipal_views.xml',

        # Vistas: libros fiscales
        'views/fiscal_book_views.xml',

        # Wizards
        'wizards/exchange_rate_wizard_view.xml',
        'wizards/fiscal_book_wizard_view.xml',
        'wizards/wh_iva_wizard_view.xml',
        'wizards/wh_islr_wizard_view.xml',
        'wizards/wh_municipal_wizard_view.xml',
        'wizards/wh_iva_txt_wizard_view.xml',
        'wizards/wh_islr_xml_wizard_view.xml',
        'wizards/other_seniat_wizards_view.xml',

        # Reportes QWeb
        'reports/report_wh_iva.xml',
        'reports/report_wh_islr.xml',
        'reports/report_wh_municipal.xml',
        'reports/report_fiscal_book.xml',
        'reports/report_invoice_forma_libre.xml',
        'reports/report_delivery_guide.xml',
        'reports/report_arcv.xml',
        'reports/report_inventory_book.xml',

        # Menús y acciones (siempre al final)
        'views/menuitems.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'l10n_ve_full/static/src/components/bcv_rate_systray.js',
            'l10n_ve_full/static/src/components/bcv_rate_systray.xml',
            'l10n_ve_full/static/src/js/account_report_currency_patch.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
