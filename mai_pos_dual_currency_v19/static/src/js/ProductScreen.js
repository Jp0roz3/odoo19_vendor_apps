/** @odoo-module */
/**
 * ProductScreen — Stock Refresh on Mount (Odoo 19)
 *
 * Después de cada venta, PaymentScreen guarda los IDs de los productos vendidos
 * en this.pos._pendingStockRefresh. Cuando ProductScreen monta (al dar clic a
 * "Nueva Orden"), lee esos IDs, consulta el stock real desde stock.quant
 * filtrado por la ubicación del POS (usando nuestro método Python dedicado)
 * y actualiza los modelos reactivos. Esto resuelve el problema de timing donde
 * el async call en PaymentScreen corre sobre un componente ya destruido.
 */
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);

        onMounted(async () => {
            await this._refreshPendingStock();
        });
    },

    async _refreshPendingStock() {
        try {
            const ids = this.pos._pendingStockRefresh;
            if (!ids || ids.length === 0) return;

            // Limpiar inmediatamente para no re-procesar
            this.pos._pendingStockRefresh = null;

            // Llamar al método Python que consulta stock.quant por ubicación POS
            const stockData = await this.env.services.orm.call(
                'product.product',
                'get_pos_stock_by_location',
                [ids, this.pos.config.id]
            );

            if (!stockData) return;

            // Actualizar product.product
            const productQtys = stockData.product || {};
            for (const pidStr of Object.keys(productQtys)) {
                const pid = parseInt(pidStr);
                const qty = productQtys[pidStr];
                const prod = this.pos.models['product.product']?.get(pid);
                if (prod) {
                    prod.qty_available = qty;
                }
            }

            // Actualizar product.template (lo que muestra el ProductCard en pantalla)
            const templateQtys = stockData.template || {};
            for (const tidStr of Object.keys(templateQtys)) {
                const tid = parseInt(tidStr);
                const qty = templateQtys[tidStr];
                const tmpl = this.pos.models['product.template']?.get(tid);
                if (tmpl) {
                    tmpl.qty_available = qty;
                }
            }

        } catch (e) {
            console.warn('[DualCurrency] ProductScreen stock refresh error:', e);
        }
    },
});
