# -*- coding: utf-8 -*-
{
    'name': 'Venezuela360: Localización Completa',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': (
        'Localización fiscal, contable y tributaria completa para Venezuela: '
        'retenciones IVA/ISLR/Municipal, libros fiscales, Unidad Tributaria histórica, '
        'territorialidad (estados/municipios/parroquias), doble moneda BS/USD con tasa BCV.'
    ),
    'description': """
Venezuela360: Localización Completa
=====================================
Módulo de localización venezolana integral para Odoo 19, desarrollado con estándares de producción.

Funcionalidades principales:
-----------------------------
- 💱 **Tasa BCV histórica**: Registro diario, trazabilidad completa, visible en todos los documentos.
- 💰 **Contabilidad Dual BS/USD**: Facturas, asientos, pagos y reportes con equivalencia automática.
- 🧾 **Retención de IVA**: Cálculo automático (75% / 100%), comprobante PDF, libro de retenciones.
- 📊 **Retención de ISLR**: Por concepto/tabla SENIAT, cálculo por sustraendo o UT, comprobante PDF.
- 🏛️ **Retención Municipal**: Por actividad económica y municipio, exportable.
- 📚 **Libros Fiscales**: Compras y ventas con exportación PDF / Excel / TXT / XML.
- 📐 **Unidad Tributaria Histórica**: Valor vigente por fecha, usado en cálculo de retenciones.
- 🗺️ **Territorialidad Venezolana**: 24 estados, municipios, parroquias vinculadas a contactos y fiscal.
- 🔢 **Numeración Fiscal**: Control de correlativo y documentos fiscales por compañía.
- ⚙️ **Multi-compañía**: Configuración independiente por empresa con soporte de múltiples monedas.

Compatibilidad:
---------------
- Odoo 19 Community & Enterprise
- Python 3.12+
- PostgreSQL 15+

Autor: JeanPerozo / Nubelco
Sitio web: https://www.nubelco.com
Soporte: soporte@nubelco.com
    """,
    'author': 'JeanPerozo / Nubelco',
    'website': 'https://www.nubelco.com',
    'support': 'soporte@nubelco.com',
    'license': 'LGPL-3',

    # -----------------------------------------------------------------
    # Dependencias
    # -----------------------------------------------------------------
    'depends': [
        'base',
        'mail',
        'account',
        'sale',
        'purchase',
        'stock',
        'base_setup',
        'contacts',
    ],

    # -----------------------------------------------------------------
    # Datos (orden obligatorio: security → datos → vistas → menús)
    # -----------------------------------------------------------------
    'data': [
        # Seguridad
        'security/ir_groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rules.xml',

        # Datos iniciales
        'data/sequence_data.xml',
        'data/territory_state_data.xml',
        'data/account_tax_group_data.xml',
        'data/ut_history_data.xml',

        # Vistas: configuración
        'views/res_config_settings_views.xml',

        # Vistas: tasa BCV
        'views/exchange_rate_views.xml',

        # Vistas: Unidad Tributaria
        'views/ut_history_views.xml',

        # Vistas: territorialidad
        'views/territory_views.xml',

        # Vistas: contactos
        'views/res_partner_views.xml',

        # Vistas: documentos contables
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/account_tax_views.xml',

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

        # Reportes
        'reports/report_wh_iva.xml',
        'reports/report_wh_islr.xml',
        'reports/report_wh_municipal.xml',
        'reports/report_fiscal_book.xml',

        # Menús y acciones (siempre al final)
        'views/menuitems.xml',
    ],

    # -----------------------------------------------------------------
    # Assets JS/CSS (Odoo 19 usa bundles declarativos en manifest)
    # -----------------------------------------------------------------
    'assets': {
        'web.assets_backend': [
            'l10n_ve_full/static/src/css/l10n_ve.css',
            'l10n_ve_full/static/src/components/bcv_rate_systray.js',
            'l10n_ve_full/static/src/components/bcv_rate_systray.xml',
        ],
    },

    # -----------------------------------------------------------------
    # Post-install
    # -----------------------------------------------------------------
    'post_init_hook': 'post_init_hook',

    # -----------------------------------------------------------------
    # Flags
    # -----------------------------------------------------------------
    'installable': True,
    'application': True,
    'auto_install': False,

    # -----------------------------------------------------------------
    # Imágenes
    # -----------------------------------------------------------------
    'images': ['static/description/banner.png'],
}
