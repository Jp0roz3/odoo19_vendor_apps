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

function patchAllReportComponents() {
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

    // 2. Parchear AccountReportControlPanel
    try {
        const panelMod = odoo.loader.modules.get("@account_reports/components/account_report/control_panel/control_panel");
        if (panelMod && panelMod.AccountReportControlPanel && !panelMod.AccountReportControlPanel._l10n_ve_patched) {
            panelMod.AccountReportControlPanel._l10n_ve_patched = true;
            patch(panelMod.AccountReportControlPanel.prototype, {
                async onSelectL10nVeCurrency(currency) {
                    const ctrl = this.controller || this.props?.controller;
                    if (ctrl && typeof ctrl.setL10nVeCurrency === "function") {
                        await ctrl.setL10nVeCurrency(currency);
                    }
                },
            });
        }
    } catch (e) {}
}

// Intentar parchear inmediatamente y periódicamente al inicio
patchAllReportComponents();

const intervalId = setInterval(patchAllReportComponents, 400);
setTimeout(() => clearInterval(intervalId), 12000);
