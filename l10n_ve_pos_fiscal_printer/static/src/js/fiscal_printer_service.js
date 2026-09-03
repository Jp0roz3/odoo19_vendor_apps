/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { TfhkaProtocol } from "./tfhka_protocol";
import { WebSerialDriver } from "./web_serial_driver";

export class FiscalPrinterService {
    constructor(env) {
        this.env = env;
        this.serialDriver = new WebSerialDriver();
        this.state = reactive({
            isConnected: false,
            connType: 'local_agent',
            agentUrl: 'http://localhost:9069',
            port: 'COM1',
            baudrate: 9600,
            model: 'srp812',
            serialNumber: '',
            lastStatus: 'Listo',
        });
    }

    initFromConfig(posConfig) {
        if (!posConfig) return;
        this.state.connType = posConfig.fiscal_printer_conn_type || 'local_agent';
        this.state.agentUrl = (posConfig.fiscal_printer_agent_url || 'http://localhost:9069').replace(/\/+$/, '');
        this.state.port = posConfig.fiscal_printer_port || 'COM1';
        this.state.baudrate = parseInt(posConfig.fiscal_printer_baudrate || 9600);
        this.state.model = posConfig.fiscal_printer_model || 'srp812';
        this.state.serialNumber = posConfig.fiscal_printer_serial || '';
    }

    getPosConfig() {
        return this.env.services.pos ? this.env.services.pos.config : null;
    }

    /**
     * Conexión / Verificación de Estado
     */
    async connect() {
        const config = this.getPosConfig();
        if (config) this.initFromConfig(config);

        if (this.state.connType === 'mock') {
            this.state.isConnected = true;
            this.state.serialNumber = "MOCK-Z1A81200";
            return { success: true, message: "Simulador fiscal conectado exitosamente." };
        }

        if (this.state.connType === 'web_serial') {
            try {
                await this.serialDriver.connect({ baudrate: this.state.baudrate });
                this.state.isConnected = true;
                return { success: true, message: "Conectado vía Web Serial API." };
            } catch (err) {
                this.state.isConnected = false;
                return { success: false, error: err.message };
            }
        }

        // Modo Agente Local (Por defecto y recomendado)
        try {
            const res = await fetch(`${this.state.agentUrl}/status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    port: this.state.port,
                    baudrate: this.state.baudrate,
                    model: this.state.model,
                }),
                signal: AbortSignal.timeout(4000)
            });

            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    this.state.isConnected = true;
                    if (data.serial) this.state.serialNumber = data.serial;
                    return { success: true, serial: data.serial, message: "Agente fiscal conectado exitosamente." };
                } else {
                    this.state.isConnected = false;
                    return { success: false, error: data.error || "Impresora no responde en el puerto especificado." };
                }
            } else {
                this.state.isConnected = false;
                return { success: false, error: `El agente fiscal respondió con código HTTP ${res.status}.` };
            }
        } catch (netErr) {
            this.state.isConnected = false;
            return {
                success: false,
                error: `No se pudo conectar al Agente Fiscal en ${this.state.agentUrl}. Verifique que el servicio local esté en ejecución en la PC de caja.`
            };
        }
    }

    async disconnect() {
        if (this.state.connType === 'web_serial') {
            await this.serialDriver.disconnect();
        }
        this.state.isConnected = false;
    }

    /**
     * Imprimir Factura Fiscal
     */
    async printInvoice(order) {
        const config = this.getPosConfig();
        if (config) this.initFromConfig(config);

        // 1. Modo Simulador
        if (this.state.connType === 'mock') {
            await new Promise(r => setTimeout(r, 1200));
            const mockNum = String(Math.floor(Math.random() * 900000) + 100000).padStart(8, '0');
            return {
                success: true,
                fiscal_invoice_number: mockNum,
                fiscal_serial: "MOCK-Z1A81200",
                message: "Factura impresa en simulador"
            };
        }

        // Construir comandos de factura
        const commands = TfhkaProtocol.buildInvoiceCommands(order);

        // 2. Modo Agente Local
        if (this.state.connType === 'local_agent') {
            try {
                const res = await fetch(`${this.state.agentUrl}/print_invoice`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        port: this.state.port,
                        baudrate: this.state.baudrate,
                        model: this.state.model,
                        commands: commands,
                    }),
                    signal: AbortSignal.timeout(30000) // 30s timeout para facturas con múltiples líneas
                });

                const data = await res.json();
                if (res.ok && data.success) {
                    return {
                        success: true,
                        fiscal_invoice_number: data.fiscal_invoice_number || 'N/A',
                        fiscal_serial: data.fiscal_serial || this.state.serialNumber || 'N/A',
                    };
                } else {
                    return {
                        success: false,
                        error: data.error || "Error al imprimir en el agente fiscal."
                    };
                }
            } catch (e) {
                return {
                    success: false,
                    error: "Error de comunicación con el agente fiscal: " + e.message
                };
            }
        }

        // 3. Modo Web Serial Directo
        if (this.state.connType === 'web_serial') {
            if (!this.state.isConnected) {
                await this.connect();
            }
            try {
                for (const cmd of commands) {
                    const r = await this.serialDriver.sendCommand(cmd);
                    if (!r.success) {
                        throw new Error(r.error || `Error enviando comando: ${cmd}`);
                    }
                    await new Promise(res => setTimeout(res, 50)); // Pacing
                }

                // Leer S1 para obtener número de factura emitido
                await new Promise(res => setTimeout(res, 800));
                const s1 = await this.serialDriver.readS1Status();
                let invoiceNum = 'N/A';
                if (s1) {
                    const match = s1.match(/\d{6,8}/);
                    if (match) invoiceNum = match[0];
                }

                return {
                    success: true,
                    fiscal_invoice_number: invoiceNum,
                    fiscal_serial: this.state.serialNumber || 'N/A'
                };
            } catch (err) {
                return { success: false, error: err.message };
            }
        }

        return { success: false, error: "Método de conexión no soportado." };
    }

    /**
     * Imprimir Reporte X
     */
    async printReportX() {
        return await this.executeSimpleCommand("I0X", "Reporte X impreso exitosamente");
    }

    /**
     * Imprimir Reporte Z
     */
    async printReportZ() {
        return await this.executeSimpleCommand("I0Z", "Reporte Z (Cierre diario) emitido exitosamente", 25000);
    }

    /**
     * Abrir Gaveta
     */
    async openDrawer() {
        return await this.executeSimpleCommand("w", "Gaveta abierta");
    }

    /**
     * Cancelar documento fiscal en curso
     */
    async cancelDocument() {
        return await this.executeSimpleCommand("7", "Documento fiscal cancelado");
    }

    /**
     * Helper para comandos simples (X, Z, Gaveta, Cancelar)
     */
    async executeSimpleCommand(cmd, successMessage, timeoutMs = 15000) {
        const config = this.getPosConfig();
        if (config) this.initFromConfig(config);

        if (this.state.connType === 'mock') {
            await new Promise(r => setTimeout(r, 1000));
            return { success: true, message: `[Simulador] ${successMessage}` };
        }

        if (this.state.connType === 'local_agent') {
            try {
                const res = await fetch(`${this.state.agentUrl}/raw_cmd`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        port: this.state.port,
                        baudrate: this.state.baudrate,
                        cmd: cmd
                    }),
                    signal: AbortSignal.timeout(timeoutMs)
                });
                const data = await res.json();
                return data;
            } catch (e) {
                return { success: false, error: e.message };
            }
        }

        if (this.state.connType === 'web_serial') {
            if (!this.state.isConnected) await this.connect();
            try {
                const res = await this.serialDriver.sendCommand(cmd, timeoutMs);
                return res.success ? { success: true, message: successMessage } : { success: false, error: res.error };
            } catch (e) {
                return { success: false, error: e.message };
            }
        }

        return { success: false, error: "Conexión no disponible." };
    }
}

export const fiscalPrinterService = {
    dependencies: ["notification"],
    start(env, { notification }) {
        const service = new FiscalPrinterService(env);
        service.notification = notification;
        return service;
    },
};

registry.category("services").add("fiscal_printer", fiscalPrinterService, { force: true });
