/** @odoo-module */
/**
 * PRODUCT IMAGE FIX — Patch directo en el modelo ProductTemplate
 * ==============================================================
 * Odoo 19 ya muestra imágenes cuando show_product_images=True.
 * Este patch hace que getImageUrl() en el modelo product.template
 * use siempre la imagen correctamente:
 *   1. Si el backend inyectó image_data_uri (base64) → úsalo (sin red)
 *   2. Si no, usa la URL estándar de Odoo (igual que nativo)
 *
 * Al patchear el MODELO (no el componente), funciona aunque el
 * template o el IndexedDB cambien.
 */

import { ProductTemplate } from "@point_of_sale/app/models/product_template";
import { patch } from "@web/core/utils/patch";

patch(ProductTemplate.prototype, {
    /**
     * Devuelve la URL/data-URI de la imagen del producto.
     * Prioridad:
     *   1. image_data_uri injected by backend (base64 data URI — sin red, bypasea SW)
     *   2. URL estándar Odoo (igual que el nativo, sin cambios)
     */
    getImageUrl() {
        // Prioridad 1: data URI base64 (inyectado por el backend Python)
        // Completamente offline, no depende del Service Worker
        if (this.image_data_uri) {
            return this.image_data_uri;
        }
        // Prioridad 2: URL estándar de Odoo (comportamiento nativo)
        return `/web/image?model=product.template&field=image_128&id=${this.id}&unique=${this.write_date}`;
    },
});
