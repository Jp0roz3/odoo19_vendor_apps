/** @odoo-module **/
/**
 * Venezuela360: Indicador BCV en Systray
 * =======================================
 * Muestra la tasa BCV oficial vigente (Bs/USD) en la barra superior de Odoo.
 * Lee siempre desde la BD (l10n_ve.exchange.rate) y se refresca cada 30 min.
 *
 * Moneda principal: USD — Moneda secundaria: Bs.F
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
            rate: "---",          // Sin fallback hardcoded: muestra "---" si no hay dato
            rateDate: "",
            loading: true,
            error: false,
        });

        onWillStart(async () => {
            await this._loadBcvRate();
        });

        onMounted(() => {
            // Refrescar la tasa cada 30 minutos (1800000 ms)
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
     * La tasa está en Bs/USD (ej: 779.9522).
     * Moneda principal es USD → mostramos cuántos Bs equivale 1 USD.
     */
    async _loadBcvRate() {
        try {
            this.state.loading = true;
            this.state.error = false;

            const today = new Date().toISOString().split("T")[0];

            // Buscar la tasa BCV más reciente para la fecha de hoy o anterior
            const rates = await this.orm.searchRead(
                "l10n_ve.exchange.rate",
                [["date", "<=", today], ["active", "=", true]],
                ["rate", "date"],
                { limit: 1, order: "date desc" }
            );

            if (rates && rates.length > 0) {
                const rateVal = rates[0].rate;
                // La tasa es Bs/USD (cuántos Bs vale 1 USD)
                // Formateamos con separadores venezolanos: 779,9522
                this.state.rate = rateVal.toLocaleString("es-VE", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 4,
                });
                this.state.rateDate = rates[0].date || "";
                this.state.error = false;
            } else {
                // No hay tasa en BD: indicar que falta sincronizar
                this.state.rate = "Sin datos";
                this.state.error = true;
            }
        } catch (e) {
            console.warn("[Venezuela360] bcv_rate_systray: Error al leer tasa BCV:", e);
            this.state.rate = "Error";
            this.state.error = true;
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Al hacer clic en el systray: forzar sincronización inmediata con BCV.
     */
    async onClickSync() {
        try {
            await this.orm.call("l10n_ve.exchange.rate", "cron_sync_bcv_rate", []);
            await this._loadBcvRate();
        } catch (e) {
            console.warn("[Venezuela360] Error al sincronizar tasa BCV:", e);
        }
    }
}

export const bcvRateSystrayItem = {
    Component: BcvRateSystray,
};

registry.category("systray").add("bcv_rate_systray", bcvRateSystrayItem, { sequence: 1 });
