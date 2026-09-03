# -*- coding: utf-8 -*-
{
    'name': 'Venezuela: POS Fiscal Printer (Bixolon SRP-812 / TFHKA)',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Impresión fiscal directa para Bixolon SRP-812, DT230, HKA80, Dascom PP9. Cumplimiento SENIAT, Cierres X y Z, puertos Serial COM/USB y Agente Local.',
    'description': """
Impresora Fiscal Punto de Venta Venezuela (SENIAT)
==================================================
Módulo profesional de integración e impresión fiscal homologado para Odoo 19.

Características Principales:
----------------------------
* Soporte nativo para Bixolon SRP-812, Bixolon DT-230, The Factory HKA-80, Dascom PP9 / PP9-Plus.
* Protocolo binario TFHKA con verificación estricta de redundancia longitudinal (LRC) y secuenciado '0'/'1'.
* Tres métodos de conectividad:
    1. Agente Fiscal Local en PC de Caja (http://localhost:8069) - Máxima estabilidad y compatibilidad con COM/USB.
    2. Conexión Web Serial API directa en Google Chrome / Microsoft Edge con control DTR/RTS.
    3. Red Local TCP/IP directa.
    4. Simulador Virtual (Modo pruebas).
* Cálculo y mapeo exacto de tasas SENIAT:
    - General (16%)
    - Reducida (8%)
    - Adicional (31%)
    - Exento (0%)
    - IGTF Percibido en Divisas
* Facturas Fiscales y Notas de Crédito / Devoluciones.
* Emisión y registro de Cierres Z y Reportes X con almacenamiento del número fiscal en la sesión y en la orden.
* Apertura de gaveta de dinero.
* Registro de número de factura fiscal, número de control y serial de máquina en `pos.order` y `account.move`.
""",
    'author': 'Antigravity / Nubelco',
    'website': 'https://github.com/Jp0roz3/odoo19_vendor_apps',
    'license': 'OPL-1',
    'depends': [
        'point_of_sale',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_config_views.xml',
        'views/pos_order_views.xml',
        'views/res_config_settings_views.xml',
        'wizards/pos_fiscal_reports_wizard_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_ve_pos_fiscal_printer/static/src/js/tfhka_protocol.js',
            'l10n_ve_pos_fiscal_printer/static/src/js/web_serial_driver.js',
            'l10n_ve_pos_fiscal_printer/static/src/js/fiscal_printer_service.js',
            'l10n_ve_pos_fiscal_printer/static/src/js/fiscal_printer_popup.js',
            'l10n_ve_pos_fiscal_printer/static/src/js/fiscal_control_buttons.js',
            'l10n_ve_pos_fiscal_printer/static/src/js/pos_payment_override.js',
            'l10n_ve_pos_fiscal_printer/static/src/xml/fiscal_printer_popup.xml',
            'l10n_ve_pos_fiscal_printer/static/src/xml/fiscal_control_buttons.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
