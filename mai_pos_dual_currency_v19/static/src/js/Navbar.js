/** @odoo-module */
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted } from "@odoo/owl";
import { UsdCashMovePopup } from "./UsdCashMovePopup";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { _t } from "@web/core/l10n/translation";
import { getRateLabel, priceOverrides } from "./dual_currency_utils";

patch(Navbar.prototype, {
    async onUsdCashMoveButtonClick() {
        this.dialog.add(UsdCashMovePopup);
    },
    async syncRate() {
        try {
            const latestConfig = await this.env.services.orm.read('pos.config', [this.pos.config.id], ['show_currency_rate']);
            if (latestConfig && latestConfig.length > 0) {
                this.pos.config.show_currency_rate = latestConfig[0].show_currency_rate;
                this.env.services.notification.add(
                    _t('Tasa actualizada: ') + this.pos.config.show_currency_rate,
                    { type: 'success', sticky: false }
                );
            }
        } catch (error) {
            console.error('[DualCurrency] Failed to sync rate:', error);
            this.env.services.notification.add(
                _t('No se pudo sincronizar la tasa. Verifique la conexion.'),
                { type: 'warning', sticky: false }
            );
        }
    },
    async syncProducts() {
        try {
            this.env.services.ui.block();
            
            // 1. Fetch updated IDs and lst_price to compare
            const productRecords = await this.env.services.orm.searchRead(
                'product.product',
                [['available_in_pos', '=', true]],
                ['id', 'lst_price']
            );
            
            let idsToUpdate = [];
            if (productRecords && productRecords.length > 0) {
                const productModels = this.pos.models ? this.pos.models['product.product'] : null;
                const dbProducts = this.pos.db ? this.pos.db.product_by_id : null;

                for (let p of productRecords) {
                    let pos_product = null;
                    if (productModels) {
                        if (typeof productModels.get === 'function') {
                            pos_product = productModels.get(p.id);
                        } else if (Array.isArray(productModels)) {
                            pos_product = productModels.find(item => item.id === p.id);
                        }
                    } else if (dbProducts) {
                        pos_product = dbProducts[p.id];
                    }

                    // Detect if update is needed. 
                    // Odoo 19 WebSockets might have already updated pos_product.lst_price, 
                    // leaving pos_product.allPrices STALE! We must check both.
                    const staleBasePrice = pos_product.allPrices?.priceWithoutTax ?? pos_product.lst_price;
                    const isStale = (pos_product.lst_price !== p.lst_price) || 
                                    (staleBasePrice !== undefined && Math.abs(staleBasePrice - p.lst_price) > 0.001);

                    if (isStale) {
                        idsToUpdate.push(p.id);

                        // 1. Calculate ratio of price change using the stale base
                        const oldPrice = staleBasePrice || 1; // avoid div by 0
                        const ratio = p.lst_price / oldPrice;

                        // 2. Proporcionalmente actualizamos allPrices sin depender del servidor
                        if (pos_product.allPrices) {
                            const newAllPrices = { ...pos_product.allPrices };
                            if (newAllPrices.priceWithTax !== undefined) {
                                newAllPrices.priceWithTax *= ratio;
                            }
                            if (newAllPrices.priceWithoutTax !== undefined) {
                                newAllPrices.priceWithoutTax *= ratio;
                            }
                            pos_product.allPrices = newAllPrices; 
                        }

                        // 3. Update core fields
                        pos_product.lst_price = p.lst_price;
                        if (p.list_price !== undefined) pos_product.list_price = p.list_price;
                    }
                    
                    // UNCONDITIONAL REACTIVITY TRIGGER:
                    // Even if isStale is false (because WebSocket silently updated memory),
                    // we MUST write to priceOverrides so OWL knows it changed and re-renders the frozen ProductCard!
                    if (pos_product && pos_product.allPrices) {
                        priceOverrides[p.id] = { ...pos_product.allPrices };
                    }
                }
            }

            // 3. Forzar el re-render de la UI
            if (this.pos.setSelectedCategoryId && this.pos.selectedCategoryId !== undefined) {
                const currentCat = this.pos.selectedCategoryId;
                // If we are already on 0, switch to a different one temporarily
                const tempCat = currentCat === 0 ? (this.pos.db?.get_category_childs_ids?.(0)?.[0] || 1) : 0;
                
                this.pos.setSelectedCategoryId(tempCat);
                setTimeout(() => {
                    this.pos.setSelectedCategoryId(currentCat);
                }, 50);
            }

            if (this.pos.get_order && this.pos.get_order()) {
                this.pos.get_order().trigger('change');
            }

            this.env.services.notification.add(
                _t(`Se sincronizaron ${idsToUpdate.length} productos modificados exitosamente.`),
                { type: 'success', sticky: false }
            );
        } catch (error) {
            console.error('[DualCurrency] Failed to sync products:', error);
            this.env.services.notification.add(
                _t('Error al sincronizar: ') + (error.message || error),
                { type: 'danger', sticky: false }
            );
            // Fallback
            if (confirm(_t('Para intentar forzar la actualización, la página se recargará. ¿Desea continuar?'))) {
                window.location.reload(true);
            }
        } finally {
            this.env.services.ui.unblock();
        }
    },
    getRateLabel() {
        if (!this.pos.config || !this.pos.config.show_dual_currency) return "";
        return getRateLabel(this.pos);
    },
    async closeSession() {
        try {
            if (this.pos && this.pos.config) {
                const updatedConfig = await this.env.services.orm.read('pos.config', [this.pos.config.id], ['show_currency_rate', 'show_dual_currency']);
                if (updatedConfig && updatedConfig.length > 0) {
                    this.pos.config.show_currency_rate = updatedConfig[0].show_currency_rate;
                    this.pos.config.show_dual_currency = updatedConfig[0].show_dual_currency;
                }
            }

            const info = await this.pos.getClosePosInfo();

            try {
                this.dialog.add(ClosePosPopup, { ...info });
            } catch (popupErr) {
                console.error('[DualCurrency] Error adding ClosePosPopup:', popupErr);
                this.env.services.notification.add(
                    _t('Error al intentar abrir el popup de cierre: ') + popupErr.message,
                    { type: 'danger', sticky: true }
                );
            }
        } catch (e) {
            console.error('[DualCurrency] Error in closeSession:', e);
            this.env.services.notification.add(
                _t('Error al cargar la informacion de cierre: ') + e.message,
                { type: 'danger', sticky: true }
            );
        }
    }
});
