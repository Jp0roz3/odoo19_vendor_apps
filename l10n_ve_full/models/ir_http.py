# -*- coding: utf-8 -*-
# ir_http.py - DESACTIVADO INTENCIONALMENTE
#
# Venezuela360: El override de ir.http causaba AttributeError en Odoo 19
# porque _get_nearest_lang no existe en la clase base ir.http de esta versión.
# Los idiomas es/es_VE se manejan exclusivamente via res_lang_data.xml
# y el post_init_hook, que es el método correcto y seguro en Odoo 19.
#
# NO BORRAR ESTE ARCHIVO - está importado en __init__.py
# Autor: JeanPerozo / Nubelco
