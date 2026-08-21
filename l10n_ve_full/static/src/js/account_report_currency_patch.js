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

function patchReportComponents() {
    // 1. Parchear AccountReport
    try {
        const reportMod = odoo.loader.modules.get("@account_reports/components/account_report/account_report");
        if (reportMod && reportMod.AccountReport && !reportMod.AccountReport._l10n_ve_patched) {
            reportMod.AccountReport._l10n_ve_patched = true;
            patch(reportMod.AccountReport.prototype, {
                async setL10nVeCurrency(currency) {
                    if (!this.options) return;
                    this.options.l10n_ve_currency = currency;
                    this.options.l10n_ve_currency_label = currency === 'bs' ? 'Bs.F' : '$';
                    this.options.l10n_ve_badge_label = currency === 'bs' ? 'En .Bs.F' : 'En .$';

                    const newOptions = {
                        ...this.options,
                        l10n_ve_currency: currency,
                        l10n_ve_currency_label: currency === 'bs' ? 'Bs.F' : '$',
                        l10n_ve_badge_label: currency === 'bs' ? 'En .Bs.F' : 'En .$',
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
    } catch (e) {}

    // 2. Parchear AccountReportFilters
    try {
        const filtersMod = odoo.loader.modules.get("@account_reports/components/account_report/filters/filters");
        if (filtersMod && filtersMod.AccountReportFilters && !filtersMod.AccountReportFilters._l10n_ve_patched) {
            filtersMod.AccountReportFilters._l10n_ve_patched = true;
            patch(filtersMod.AccountReportFilters.prototype, {
                async selectL10nVeCurrency(currency) {
                    const ctrl = this.controller || this.props?.controller || this.env?.controller;
                    if (ctrl && typeof ctrl.setL10nVeCurrency === "function") {
                        await ctrl.setL10nVeCurrency(currency);
                    }
                },
            });
        }
    } catch (e) {}
}

// Inyección y listener dinámico en el DOM como seguro de vida visual
function setupDynamicDomWatcher() {
    document.addEventListener("click", async (e) => {
        const target = e.target.closest(".l10n_ve_currency_menu_item");
        if (target) {
            e.preventDefault();
            const currency = target.getAttribute("data-currency") || "bs";
            // Buscar la instancia activa del reporte en OWL o disparar reload
            const filterEl = target.closest(".o_account_reports_filters") || document.querySelector(".o_account_reports_filters");
            if (filterEl && window.__owl__) {
                const node = filterEl.__owl__ || target.closest(".o_account_reports_page")?.__owl__;
                if (node && node.component) {
                    const ctrl = node.component.controller || node.component;
                    if (ctrl && typeof ctrl.setL10nVeCurrency === "function") {
                        await ctrl.setL10nVeCurrency(currency);
                        return;
                    }
                }
            }
        }
    });
}

patchReportComponents();
setupDynamicDomWatcher();

const intervalId = setInterval(patchReportComponents, 500);
setTimeout(() => clearInterval(intervalId), 15000);
