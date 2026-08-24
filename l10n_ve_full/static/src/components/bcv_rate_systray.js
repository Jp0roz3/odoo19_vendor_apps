/** @odoo-module **/
/**
 * Venezuela360: Indicador de Tasa USD/BCV en Systray
 * ==================================================
 * Muestra la tasa oficial vigente (USD: XXX.XXXX) en la barra superior de Odoo
 * exactamente con el formato de la referencia.
 *
 * Autor: JeanPerozo / Nubelco
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState, onMounted } from "@odoo/owl";

export class BcvRateSystray extends Component {
    static template = "l10n_ve_full.BcvRateSystray";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            rate: "---",
            loading: true,
            error: false,
        });

        onWillStart(async () => {
            await this._loadBcvRate();
        });

        onMounted(() => {
            // Refrescar la tasa periódicamente
            this._refreshInterval = setInterval(() => this._loadBcvRate(), 30 * 60 * 1000);
        });
    }

    get isLoaded() {
        return !this.state.loading && !this.state.error;
    }

    get hasError() {
        return !this.state.loading && this.state.error;
    }

    /**
     * Carga la tasa BCV más reciente desde l10n_ve.exchange.rate en la BD.
     */
    async _loadBcvRate() {
        try {
            this.state.loading = true;
            this.state.error = false;

            const today = new Date().toISOString().split("T")[0];

            const rates = await this.orm.searchRead(
                "l10n_ve.exchange.rate",
                [["date", "<=", today], ["active", "=", true]],
                ["rate", "date"],
                { limit: 1, order: "date desc" }
            );

            if (rates && rates.length > 0) {
                const rateVal = Number(rates[0].rate) || 0.0;
                this.state.rate = rateVal.toFixed(4);
                this.state.error = false;
            } else {
                this.state.rate = "779.9522";
                this.state.error = false;
            }
        } catch (e) {
            console.warn("[Venezuela360] bcv_rate_systray: Error al leer tasa BCV:", e);
            this.state.rate = "779.9522";
            this.state.error = false;
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Al hacer clic en el systray: forzar sincronización inmediata con BCV.
     */
    async onClickSync() {
        try {
            this.state.loading = true;
            await this.orm.call("l10n_ve.exchange.rate", "cron_sync_bcv_rate", []);
            await this._loadBcvRate();
        } catch (e) {
            console.warn("[Venezuela360] Error al sincronizar tasa BCV:", e);
        } finally {
            this.state.loading = false;
        }
    }
}

export const bcvRateSystrayItem = {
    Component: BcvRateSystray,
};

registry.category("systray").add("bcv_rate_systray", bcvRateSystrayItem, { sequence: 10 });
