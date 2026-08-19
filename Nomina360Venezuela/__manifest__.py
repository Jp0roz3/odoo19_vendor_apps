# -*- coding: utf-8 -*-
{
    'name': 'Nomina 360 Venezuela - Nómina Legal y Doble Moneda (Odoo 19)',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Gestión Integral de Nómina Venezolana en Bs y $ USD (LOTTT, IVSS, FAOV, INCES, Ley de Pensiones 2024, TodoTicket Cestaticket TXT, Prestaciones Sociales, Disquetes Bancarios).',
    'description': """
Nomina 360 Venezuela (Odoo 19)
===============================
Módulo Enterprise definitivo para la gestión de nómina laboral en Venezuela.
Desarrollado por JeanPerozo/Nubelco para superar a sistemas tradicionales como Profit Plus Nómina.

Características Principales:
-----------------------------
* 💳 **Abonos Cestaticket TodoTicket**: Generación en 1-click del archivo plano TXT con trama de 41 caracteres.
* 💵 **Gestión Multimoneda Dual (Bs. / $ USD)**: Configuración en Dólares convertida automáticamente a tasa BCV.
* 🏛️ **Cumplimiento Parafiscal Venezolano**: IVSS (SSO y SPF), FAOV (Banavih), INCES y Ley de Pensiones 2024 (9%).
* 📈 **Prestaciones Sociales e Intereses**: Acumulados Art. 142 LOTTT e intereses sobre prestaciones.
* 🏦 **Disquetes Bancarios Directos**: Exportación de pagos masivos para Banesco, Mercantil, BDV y Provincial.
* 🏖️ **Vacaciones, Utilidades y Liquidaciones**: Procesamiento integral anual y terminaciones de contrato.

Soporte Comercial e Implementación: JeanPerozo / Nubelco (https://www.nubelco.com)
    """,
    'author': 'JeanPerozo / Nubelco',
    'website': 'https://www.nubelco.com',
    'support': 'soporte@nubelco.com',
    'license': 'OPL-1',
    'price': 3840.00,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
    'depends': [
        'hr',
        'account',
        'contacts',
        'mail',
        'calendar',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/bank_payroll_export_wizard_views.xml',
        'wizard/hr_payroll_novelties_wizard_views.xml',
        'wizard/legal_reports_wizard_views.xml',
        'wizard/arc_seniat_email_wizard_views.xml',
        'wizard/hr_payroll_migration_wizard_views.xml',
        'data/hr_payroll_structure_type_data.xml',
        'data/hr_payroll_structure_data.xml',
        'data/hr_salary_rules_data.xml',
        'data/hr_payslip_todoticket_sequence.xml',
        'views/hr_contract_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/hr_prestaciones_views.xml',
        'views/hr_loan_views.xml',
        'views/hr_liquidacion_views.xml',
        'views/hr_provisiones_views.xml',
        'views/hr_innovations_views.xml',
        'views/hr_payslip_todoticket_views.xml',
        'views/res_config_settings_views.xml',
        'views/menuitems.xml',
        'report/report_payslip_template.xml',
        'report/report_liquidacion_template.xml',
        'report/report_contract_template.xml',
        'report/report_loan_template.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'assets': {},
}
