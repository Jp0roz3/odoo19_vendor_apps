/** @odoo-module **/
/**
 * Venezuela360: Selector Bimoneda [💱 Moneda: Bs.F / $] en Reportes Financieros
 * ==============================================================================
 * Conecta el selector de moneda interactivo con el controlador AccountReport
 * de Odoo Enterprise, permitiendo alternar al instante entre Bs.F y USD.
 *
 * Autor: JeanPerozo / Nubelco
 */

import { patch } from "@web/core/utils/patch";

// Intentar importar AccountReport si está disponible en el bundle
let AccountReportComponent = null;
try {
    const mod = odoo.loader.modules.get("@account_reports/components/account_report/account_report");
    if (mod && mod.AccountReport) {
        AccountReportComponent = mod.AccountReport;
    }
} catch (e) {
    // Si no está cargado inmediatamente, se parcheará en diferido
}

function applyReportPatch(AccountReportClass) {
    if (!AccountReportClass || AccountReportClass._l10n_ve_patched) {
        return;
    }
    AccountReportClass._l10n_ve_patched = true;

    patch(AccountReportClass.prototype, {
        /**
         * Cambia la moneda activa del reporte ('bs' o 'usd') y solicita la recarga.
         */
        async setL10nVeCurrency(currency) {
            if (!this.options || this.options.l10n_ve_currency === currency) {
                return;
            }
            const newOptions = {
                ...this.options,
                l10n_ve_currency: currency,
                l10n_ve_currency_label: currency === 'bs' ? 'Bs.F' : '$',
                l10n_ve_badge_label: currency === 'bs' ? 'En .Bs.F' : 'En $',
            };

            if (typeof this.reload === "function") {
                await this.reload({ options: newOptions });
            } else if (typeof this.updateOptions === "function") {
                await this.updateOptions(newOptions);
            } else if (this.controller && typeof this.controller.reload === "function") {
                await this.controller.reload({ options: newOptions });
            }
        },
    });
}

if (AccountReportComponent) {
    applyReportPatch(AccountReportComponent);
} else {
    // Escuchar cuando se carguen los módulos OWL en frontend
    const checkInterval = setInterval(() => {
        try {
            const mod = odoo.loader.modules.get("@account_reports/components/account_report/account_report");
            if (mod && mod.AccountReport) {
                applyReportPatch(mod.AccountReport);
                clearInterval(checkInterval);
            }
        } catch (e) {}
    }, 300);

    setTimeout(() => clearInterval(checkInterval), 10000);
}
