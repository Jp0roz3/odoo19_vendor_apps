# -*- coding: utf-8 -*-
# Orden de importación respeta dependencias entre modelos:
# 1. Modelos independientes (sin FK entre sí)
# 2. Modelos que extienden ORM nativo de Odoo
# 3. Modelos de documentos (dependen de partner, company, tax)
# 4. Modelos de retención (dependen de account.move)
# 5. Libros fiscales (dependen de todo lo anterior)
import sys

from . import territory          # estados, municipios, parroquias (sin deps)
from . import exchange_rate      # tasa de cambio histórica BCV (sin deps)
from . import ut_history         # Unidad Tributaria histórica (depende de company)
from . import res_company        # extiende res.company (depende de territory, exchange_rate)
from . import res_partner        # extiende res.partner (depende de territory)
from . import ir_http            # extensión de ir.http para resolución segura de idioma
from . import account_tax        # extiende account.tax (localización venezolana)
from . import account_move       # extiende account.move (campos BS/USD, retenciones)
from . import account_payment    # extiende account.payment (dual currency)
from . import withholding_iva    # retención de IVA (depende de account.move)
from . import withholding_islr   # retención de ISLR (depende de account.move, ut_history)
from . import withholding_municipal  # retención municipal (depende de territory, account.move)
from . import fiscal_book        # libros fiscales (depende de todo lo anterior)
from . import res_config_settings  # extensión de ajustes (relaciona campos de company)
from . import account_journal      # extensión del diario (dashboard bimoneda dual)
from . import product_template     # extensión de productos (precios duales Bs/USD)
from . import account_report       # extensión de reportes contables bimoneda dual
from . import control_number_sequence  # gestión de talonarios y secuencias de control fiscal

from . import sale_order
from . import purchase_order
from . import stock_picking

