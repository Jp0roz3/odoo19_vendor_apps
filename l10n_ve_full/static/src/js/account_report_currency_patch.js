/** @odoo-module **/
/**
 * Venezuela360: Selector Bimoneda [💵 Moneda: Bs.F / $]
 * =======================================================
 * Inyecta el dropdown de moneda en la barra superior de reportes financieros
 * de Odoo Enterprise usando el registry de filtros de account_reports.
 *
 * Autor: JeanPerozo / Nubelco
 */

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { Component, xml } from "@odoo/owl";

// ── Componente del Botón Desplegable de Moneda ──────────────────────────────
class L10nVeCurrencyFilter extends Component {
    static template = xml`
        <div t-if="props.options and props.options.filter_l10n_ve_currency"
             class="btn-group dropdown ms-1">
            <button class="btn btn-outline-primary dropdown-toggle px-2 py-1"
                    style="font-size: 12px;"
                    data-bs-toggle="dropdown"
                    aria-expanded="false">
                <i class="fa fa-exchange me-1"/>
                Moneda:
                <strong t-attf-style="color: {{ props.options.l10n_ve_currency === 'usd' ? '#dc3545' : '#198754' }};">
                    <t t-out="props.options.l10n_ve_currency === 'usd' ? '$' : 'Bs.F'"/>
                </strong>
            </button>
            <ul class="dropdown-menu dropdown-menu-end shadow">
                <li class="dropdown-item-text fw-bold text-muted small">Seleccionar moneda</li>
                <li><hr class="dropdown-divider m-0"/></li>
                <li>
                    <a class="dropdown-item d-flex align-items-center gap-2"
                       href="#"
                       t-on-click.prevent="() => props.setCurrency('bs')">
                        <i t-att-class="props.options.l10n_ve_currency !== 'usd' ? 'fa fa-check text-success' : 'fa fa-circle-o text-muted'"/>
                        <span>Bs.F (Bolívares)</span>
                    </a>
                </li>
                <li>
                    <a class="dropdown-item d-flex align-items-center gap-2"
                       href="#"
                       t-on-click.prevent="() => props.setCurrency('usd')">
                        <i t-att-class="props.options.l10n_ve_currency === 'usd' ? 'fa fa-check text-success' : 'fa fa-circle-o text-muted'"/>
                        <span>$ (Dólares USD)</span>
                    </a>
                </li>
            </ul>
        </div>
        <span t-if="props.options and props.options.l10n_ve_badge_label"
              class="badge rounded-pill ms-1"
              t-attf-style="background-color: {{ props.options.l10n_ve_currency === 'usd' ? '#dc3545' : '#198754' }}; font-size: 11px;">
            <t t-out="props.options.l10n_ve_badge_label"/>
        </span>
    `;

    static props = {
        options: Object,
        setCurrency: Function,
    };
}

// ── Patch sobre el Controlador de Reportes Contables ─────────────────────────
// Intentar parchear dinámicamente el controlador de Enterprise
function tryPatchAccountReport() {
    const reportMod = registry.category("main_components")?.content || {};

    // Buscar el módulo account_reports en el loader
    const moduleName = "@account_reports/components/account_report/account_report";
    if (!odoo.__DEBUG__?.services && !window.__owl__) return;

    // Acceder al módulo vía loader de Odoo
    const loaderGet = (name) => {
        try {
            return odoo.loader.modules.get(name);
        } catch {
            return null;
        }
    };

    const mod = loaderGet(moduleName);
    if (!mod) return;

    const { AccountReport } = mod;
    if (!AccountReport) return;

    patch(AccountReport.prototype, {
        /**
         * Cambia la moneda del reporte recargando con las nuevas opciones.
         */
        async setL10nVeCurrency(currency) {
            if (!this.options || this.options.l10n_ve_currency === currency) {
                return;
            }
            const newOptions = {
                ...this.options,
                l10n_ve_currency: currency,
            };
            if (this.reload) {
                await this.reload({ options: newOptions });
            } else if (this.updateOptions) {
                await this.updateOptions(newOptions);
            }
        },
    });
}

// Ejecutar después de que OWL y los módulos estén listos
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(tryPatchAccountReport, 500));
} else {
    setTimeout(tryPatchAccountReport, 500);
}
