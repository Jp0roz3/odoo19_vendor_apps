# 🇻🇪 MANUAL MAESTRO DE CAPACITACIÓN: LOCALIZACIÓN VENEZOLANA ODOO 19 (`l10n_ve_full`)
**Versión del Sistema:** Odoo Enterprise 19.0 / Community 19.0  
**Módulo:** `l10n_ve_full` (Localización Integral Venezuela 2026)  
**Marco Legal y Normativo:** SENIAT (Providencias SNAT/2011/00071, SNAT/2015/00049, SNAT/2022/000013, Decreto 1.808 ISLR, Gaceta Oficial Nº 42.339 IGTF).

---

## 📑 ÍNDICE DE CONTENIDOS

1. [Arquitectura General y Requisitos Previos](#1-arquitectura-general-y-requisitos-previos)
2. [Configuración de la Compañía y Parámetros Fiscales](#2-configuración-de-la-compañía-y-parámetros-fiscales)
3. [Tasa de Cambio BCV y Motor Bimoneda (USD / Bs.)](#3-tasa-de-cambio-bcv-y-motor-bimoneda-usd--bs)
4. [Plan Contable SENIAT y Catálogo de Cuentas](#4-plan-contable-seniat-y-catálogo-de-cuentas)
5. [Estructura de Impuestos Nacionales (IVA, IGTF, Exenciones)](#5-estructura-de-impuestos-nacionales-iva-igtf-exenciones)
6. [Diarios Contables y Secuencias Fiscales](#6-diarios-contables-y-secuencias-fiscales)
7. [Fichas de Contactos: Clientes, Proveedores y Tipos de Persona](#7-fichas-de-contactos-clientes-proveedores-y-tipos-de-persona)
8. [Ciclo de Ventas y Facturación Fiscal (AR)](#8-ciclo-de-ventas-y-facturación-fiscal-ar)
9. [Ciclo de Compras y Recepción de Facturas de Proveedor (AP)](#9-ciclo-de-compras-y-recepción-de-facturas-de-proveedor-ap)
10. [Módulo de Retenciones de IVA (Comprobante y TXT SENIAT)](#10-módulo-de-retenciones-de-iva-comprobante-y-txt-seniat)
11. [Módulo de Retenciones de ISLR (Conceptos, Decreto 1808 y XML)](#11-módulo-de-retenciones-de-islr-conceptos-decreto-1808-y-xml)
12. [Módulo de Retenciones Municipales (Actividades Económicas)](#12-módulo-de-retenciones-municipales-actividades-económicas)
13. [Régimen Especial IGTF 3% en Pagos en Divisas](#13-régimen-especial-igtf-3-en-pagos-en-divisas)
14. [Libros Fiscales Oficiales (Ventas y Compras en Excel/PDF)](#14-libros-fiscales-oficiales-ventas-y-compras-en-excelpdf)
15. [Conciliación Bancaria y Diferencial Cambiario Automático](#15-conciliación-bancaria-y-diferencial-cambiario-automático)
16. [Preguntas Frecuentes y Resolución de Incidencias Técnicas](#16-preguntas-frecuentes-y-resolución-de-incidencias-técnicas)

---

## 1. Arquitectura General y Requisitos Previos

El módulo `l10n_ve_full` transforma Odoo 19 en un ERP 100% adaptado a la legislación tributaria, contable y cambiaria de la República Bolivariana de Venezuela.

### Principios Fundamentales de Diseño:
* **Bimoneda Nativa:** Soporta operación en Bolívares (VES) como moneda de curso legal y Dólares Estadounidenses (USD) como moneda de cuenta/referencia sin distorsión contable.
* **Integridad Fiscal SENIAT:** Generación automática de número de control fiscal correlativo, número de factura, comprobantes de retención (IVA, ISLR, Municipal) y archivos de transmisión electrónica oficial (.TXT y .XML).
* **Bloqueo de Modificaciones Posteriores:** Conforme a la Providencia 00071, las facturas validadas con número de control no permiten alteración de montos o bases imponibles.

---

## 2. Configuración de la Compañía y Parámetros Fiscales

Para iniciar la configuración, ingrese a **Ajustes ➔ Empresas ➔ [Seleccionar su Empresa]**:

### 2.1 Datos de Identificación Fiscal
| Campo | Formato Requerido | Descripción |
| :--- | :--- | :--- |
| **Nombre de la Compañía** | Razón Social Exacta | Nombre legal registrado en el Registro Mercantil. |
| **RIF (`vat`)** | `J-12345678-9` o `G-12345678-9` | Registro de Información Fiscal con guiones. |
| **Tipo de Persona** | Jurídica Domiciliada / Natural | Determina las tablas de retención ISLR por defecto. |
| **Dirección Fiscal** | Completa con Municipio y Estado | Requerida en el encabezado de todos los reportes fiscales. |

### 2.2 Pestaña Localización Venezolana
Diríjase a la pestaña **Localización Venezuela** dentro del formulario de la compañía o en **Contabilidad ➔ Ajustes**:
1. **Contribuyente Especial:** Marque esta casilla si la empresa ha sido notificada por el SENIAT como Sujeto Pasivo Especial (Agente de Retención).
2. **Porcentaje de Retención IVA por Defecto:** Seleccione `75%` (general) o `100%` (cuando aplique según providencia).
3. **Moneda Base Contable:** Defina si la contabilidad principal opera en `USD` (recomendado para estabilidad financiera) o en `VES` (Bolívares).
4. **Cuenta de IGTF por Cobrar / Pagar:** Asigne las cuentas contables `2.1.04.01.xxx` para el registro automático de IGTF.

---

## 3. Tasa de Cambio BCV y Motor Bimoneda (USD / Bs.)

El sistema sincroniza o permite la actualización manual y automática de la tasa oficial publicada por el **Banco Central de Venezuela (BCV)**.

### 3.1 Actualización de Tasa de Cambio
1. Vaya a **Contabilidad ➔ Configuración ➔ Monedas ➔ USD (Dólar)**.
2. En la pestaña **Tasas**, registre la tasa vigente fijada por el BCV:
   * **Fecha:** Fecha valor de la tasa.
   * **Tasa Inversa:** Ingrese el monto en Bolívares por Dólar (Ej: `791.3248`).
   * **Tasa Odoo:** Se calculará automáticamente como `1 / 791.3248 = 0.001263704...`.
3. Al emitir o recibir documentos, Odoo fijará la tasa del día de la factura (`l10n_ve_currency_rate`), congelándola para garantizar que los comprobantes de retención y libros fiscales reflejen exactamente la tasa a la fecha del hecho imponible.

---

## 4. Plan Contable SENIAT y Catálogo de Cuentas

El módulo incluye el catálogo de cuentas estándar venezolano estructurado bajo NIIF y requerimientos SENIAT:

```text
1.0.0.00.000 ACTIVO
├── 1.1.0.00.000 ACTIVO CORRIENTE
│   ├── 1.1.01.00.000 Efectivo y Equivalentes de Efectivo
│   │   ├── 1.1.01.01.001 Caja Principal (VES)
│   │   ├── 1.1.01.01.002 Caja Moneda Extranjera (USD)
│   │   ├── 1.1.01.02.001 Banco Nacional VES
│   │   └── 1.1.01.02.002 Banco Custodia Divisas USD
│   ├── 1.1.02.00.000 Cuentas por Cobrar Comerciales
│   └── 1.1.05.00.000 Créditos Fiscales y Retenciones
│       ├── 1.1.05.01.001 Crédito Fiscal IVA (16%)
│       ├── 1.1.05.02.001 Retenciones de IVA por Cobrar (Clientes)
│       ├── 1.1.05.03.001 Retenciones de ISLR por Cobrar (Clientes)
│       └── 1.1.05.04.001 Retenciones Municipales por Cobrar
2.0.0.00.000 PASIVO
├── 2.1.0.00.000 PASIVO CORRIENTE
│   ├── 2.1.01.00.000 Cuentas por Pagar Comerciales
│   └── 2.1.04.00.000 Débitos Fiscales y Retenciones por Enterar
│       ├── 2.1.04.01.001 Débito Fiscal IVA (16%)
│       ├── 2.1.04.02.001 Retenciones de IVA por Enterar (Proveedores)
│       ├── 2.1.04.03.001 Retenciones de ISLR por Enterar (Proveedores)
│       ├── 2.1.04.04.001 Retenciones Municipales por Enterar
│       └── 2.1.04.05.001 IGTF por Enterar (3% Divisas)
```

---

## 5. Estructura de Impuestos Nacionales (IVA, IGTF, Exenciones)

Ubicación: **Contabilidad ➔ Configuración ➔ Impuestos**.

### 5.1 Catálogo de Impuestos Preconfigurados
| Impuesto | Ámbito | Tasa | Grupo Fiscal | Etiqueta Recibo |
| :--- | :--- | :--- | :--- | :--- |
| **IVA 16% Ventas** | Ventas | `16.0%` | IVA 16% General | `IVA 16%` |
| **IVA Reducido 8% Ventas** | Ventas | `8.0%` | IVA 8% Reducido | `IVA 8%` |
| **IVA Adicional 31% Ventas**| Ventas | `31.0%`| IVA 31% Suntuario | `IVA 31%` |
| **Exento de IVA Ventas** | Ventas | `0.0%` | Exento / No Sujeto | `EXENTO` |
| **IGTF 3% Percibido** | Ventas | `3.0%` | IGTF 3% Divisas | `IGTF 3%` |
| **IVA 16% Compras** | Compras | `16.0%` | IVA 16% General | `IVA 16%` |
| **IVA 8% Compras** | Compras | `8.0%` | IVA 8% Reducido | `IVA 8%` |
| **Exento Compras** | Compras | `0.0%` | Exento / No Sujeto | `EXENTO` |

---

## 6. Diarios Contables y Secuencias Fiscales

Ubicación: **Contabilidad ➔ Configuración ➔ Diarios Contables**.

### 6.1 Diarios Clave Requeridos:
1. **Facturas de Clientes (`INV`)**:
   * **Tipo:** Ventas.
   * **Secuencia de Control Fiscal:** Habilite la casilla *Secuencia de Control Fiscal Automática*.
   * **Prefijo de Control:** Ejemplo `00-` (produce `00-000001`, `00-000002`).
2. **Facturas de Proveedores (`BILL`)**:
   * **Tipo:** Compras.
   * **Control de Duplicidad:** Exige ingresar Obligatoriamente el Número de Factura del Proveedor y su Número de Control Fiscal.
3. **Diario de Retenciones IVA (`RET_IVA`)**:
   * **Tipo:** Varios / Banco.
   * **Uso:** Asiento automático de retención al validar facturas o procesar pagos.
4. **Diario de Retenciones ISLR (`RET_ISLR`)**:
   * **Tipo:** Varios.
   * **Uso:** Emisión del comprobante de retención de Impuesto Sobre la Renta.

---

## 7. Fichas de Contactos: Clientes, Proveedores y Tipos de Persona

Ubicación: **Contactos ➔ Contactos ➔ [Seleccionar Contacto]**.

### 7.1 Configuración Obligatoria para Cumplimiento Tributario
1. **Tipo de Identificación:**
   * `V`: Venezolano Natural.
   * `E`: Extranjero Natural.
   * `J`: Jurídico Nacional.
   * `G`: Gubernamental / Estado.
   * `P`: Pasaporte.
2. **Número de RIF:** Validación estricta con dígito verificador.
3. **Condición Fiscal:**
   * *Contribuyente Formal / Ordinario / Especial*.
   * Si es **Especial**, defina si retiene el `75%` o el `100%`.
4. **Tipo de Persona ISLR (Pestaña Contabilidad):**
   * `PN-R`: Persona Natural Residente (Sustraendo aplicable).
   * `PN-NR`: Persona Natural No Residente (34% directo sin sustraendo).
   * `PJ-DOM`: Persona Jurídica Domiciliada (Tablas acumulativas o 5%).
   * `PJ-NDOM`: Persona Jurídica No Domiciliada.

---

## 8. Ciclo de Ventas y Facturación Fiscal (AR)

### 8.1 Emisión de una Factura de Venta
1. Vaya a **Contabilidad ➔ Clientes ➔ Facturas ➔ Nueva**.
2. **Cliente:** Seleccione el cliente.
3. **Fecha de la Factura:** Establece el período fiscal y la tasa BCV del día.
4. **Líneas de Factura:** Agregue los productos. Odoo mostrará:
   * Precio unitario en USD.
   * Precio equivalente en Bolívares.
   * Impuestos asociados (ej. IVA 16%).
5. **Confirmar Factura:**
   * Odoo asignará automáticamente el **Número de Factura Fiscal** y el **Número de Control Fiscal**.
   * Se genera el asiento contable bimoneda.

### 8.2 Recepción de Retención de IVA de Cliente
Cuando un Cliente Contribuyente Especial nos retiene IVA:
1. En la factura abierta, haga clic en el botón **Registrar Retención de Cliente** (o desde **Contabilidad ➔ Clientes ➔ Retenciones de IVA de Clientes**).
2. Ingrese:
   * **Número de Comprobante del Cliente:** (14 dígitos, ej: `20260800000012`).
   * **Fecha del Comprobante**.
   * **Monto Retenido en Bs. y USD**.
3. Haga clic en **Validar**: La factura quedará conciliada parcialmente por el monto de la retención y el saldo pendiente para el cobro.

---

## 9. Ciclo de Compras y Recepción de Facturas de Proveedor (AP)

### 9.1 Registro de Factura de Proveedor
1. Ingrese a **Contabilidad ➔ Proveedores ➔ Facturas ➔ Nueva**.
2. **Proveedor:** Seleccione la empresa emisora.
3. **Campos Fiscales Obligatorios:**
   * **Nº de Factura Proveedor:** (Ej: `004521`).
   * **Nº de Control Fiscal Proveedor:** (Ej: `00-008954`).
   * **Nº de Nota de Débito / Crédito Afectada:** (Solo si aplica).
4. **Líneas de Gasto:** Cargue los bienes o servicios con su respectivo IVA y Concepto de Retención ISLR.
5. **Confirmar Factura:**
   * Si la empresa es **Contribuyente Especial**, el sistema generará automáticamente la **Retención de IVA de Proveedor** y la **Retención de ISLR**.

---

## 10. Módulo de Retenciones de IVA (Comprobante y TXT SENIAT)

### 10.1 Gestión de Comprobantes de Retención de IVA
* Ubicación: **Contabilidad ➔ Proveedores ➔ Retenciones de IVA**.
* Al validar la factura de compra, Odoo calcula:
  $$\text{Monto Retenido} = \text{Base Imponible} \times 16\% \times 75\% \text{ (o } 100\%)$$
* **Acciones Disponibles:**
  * **Imprimir Comprobante:** Genera el PDF oficial en formato legal SENIAT con código QR, firma y sello digital.
  * **Enviar por Correo:** Envía el comprobante al correo del proveedor automáticamente.

### 10.2 Generación del Archivo TXT para Declaración SENIAT
1. Vaya a **Contabilidad ➔ Reportes ➔ Venezuela ➔ Archivo TXT Retenciones IVA**.
2. Seleccione la **Quincena** a declarar (1ra Quincena: días 1-15 | 2da Quincena: días 16-fin de mes).
3. Haga clic en **Generar TXT**:
   * Odoo creará el archivo plano normalizado según especificación SENIAT:
   ```text
   J123456789	202608	2026-08-15	C	01	J987654321	004521	00-008954	1000.00	160.00	0	20260800000001	0.00	16.00	120.00	0
   ```
4. Cargue este archivo directamente en el portal fiscal del SENIAT sin necesidad de modificaciones manuales.

---

## 11. Módulo de Retenciones de ISLR (Conceptos, Decreto 1808 y XML)

### 11.1 Tabla de Conceptos ISLR (Decreto 1.808)
El sistema cuenta con la tabla completa de conceptos de retención:
* **Honorarios Profesionales (PN Residente):** 3% con sustraendo acumulativo de Unidades Tributarias (UT).
* **Honorarios Profesionales (PN No Residente):** 34% sin sustraendo.
* **Servicios de Mantenimiento y Ejecución de Obras (PJ Domiciliada):** 2% sobre base imponible.
* **Arrendamiento de Inmuebles Comerciales (PJ):** 5% sobre base imponible.
* **Comisiones Mercantiles (PJ):** 5% sobre base imponible.
* **Fletes y Transporte de Carga:** 3% sobre base imponible.

### 11.2 Generación del Archivo XML ISLR para Declaración Mensual
1. Vaya a **Contabilidad ➔ Reportes ➔ Venezuela ➔ Archivo XML Retenciones ISLR**.
2. Seleccione el **Mes y Año Fiscal**.
3. Haga clic en **Exportar XML**.
4. El archivo generado contiene la estructura oficial XML validada por el validador del SENIAT:
   ```xml
   <?xml version="1.0" encoding="ISO-8859-1"?>
   <RelacionRetencionesISLR RifAgente="J123456789" Periodo="202608">
     <DetalleRetencion>
       <RifRetenido>J987654321</RifRetenido>
       <NumeroFactura>004521</NumeroFactura>
       <NumeroControl>00-008954</NumeroControl>
       <FechaOperacion>15/08/2026</FechaOperacion>
       <CodigoConcepto>055</CodigoConcepto>
       <MontoOperacion>1000.00</MontoOperacion>
       <PorcentajeRetencion>2.00</PorcentajeRetencion>
     </DetalleRetencion>
   </RelacionRetencionesISLR>
   ```

---

## 12. Módulo de Retenciones Municipales (Actividades Económicas)

Para empresas designadas como agentes de retención del Impuesto sobre Actividades Económicas (Patente Municipal):

1. **Configuración de Ramos y Códigos de Actividad:**
   * En **Contabilidad ➔ Configuración ➔ Códigos de Actividad Municipal**, registre los códigos del clasificador de su Alcaldía (ej: Chacao, Sucre, Libertador, Baruta) con su alícuota en milaje (ej: `1.5%`, `2.0%`).
2. **Generación del Comprobante Municipal:**
   * Al registrar la factura de compras de un proveedor del municipio, seleccione el código de actividad.
   * El sistema calcula la retención municipal y emite el **Comprobante de Retención Municipal** imprimible para el proveedor.

---

## 13. Régimen Especial IGTF 3% en Pagos en Divisas

Conforme a la Gaceta Oficial Nº 42.339:

1. **Percepción de IGTF en Ventas:**
   * Cuando un cliente abona una factura en divisas en efectivo (USD Cash) o criptoactivos no soberanos, se cobra un recargo del **3% sobre el monto efectivamente pagado en divisas**.
   * En la pantalla de registro de pago de la factura, al seleccionar el método *Efectivo Dólares*, el sistema calcula el renglón de IGTF 3% y genera el asiento contable en la cuenta `2.1.04.05.001 (IGTF por Enterar)`.
2. **Pago de IGTF en Compras:**
   * Cuando la empresa paga a proveedores en divisas en efectivo, se contabiliza el gasto no deducible de IGTF conforme al artículo 18 de la ley.

---

## 14. Libros Fiscales Oficiales (Ventas y Compras en Excel/PDF)

Ubicación: **Contabilidad ➔ Reportes ➔ Libros Fiscales de Venezuela**.

### 14.1 Libro de Ventas
Contiene todas las columnas legalmente exigidas por el artículo 76 del Reglamento de la Ley de IVA:
* Nº de Operación correlativa mensual.
* Fecha de Factura.
* RIF y Nombre o Razón Social del Comprador.
* Nº de Factura, Nº de Control Fiscal, Nº de Nota de Débito/Crédito.
* Total Ventas Incluyendo IVA.
* Ventas Exentas o No Sujetas.
* Base Imponible General (16%), Impuesto IVA (16%).
* Base Imponible Reducida (8%), Impuesto IVA (8%).
* Base Imponible Adicional (31%), Impuesto IVA (31%).
* IVA Retenido por Clientes.
* IGTF 3% Percibido.

### 14.2 Libro de Compras
Registra las compras y recepciones de servicios con detalle de:
* Compras Internas Gravadas, Exentas y de Importación.
* Crédito Fiscal Total y Crédito Fiscal Deducible.
* Retenciones de IVA practicadas a Proveedores.
* Formato de Exportación disponible en **Excel (.XLSX) con fórmulas dinámicas** y **PDF Oficial de Imprenta**.

---

## 15. Conciliación Bancaria y Diferencial Cambiario Automático

1. **Registro de Movimientos Bancarios:**
   * Cuentas en Divisas (USD): Registran entradas/salidas en USD y calculan el contra-valor en VES a la tasa BCV del día.
   * Cuentas en Bolívares (VES): Registran cobros/pagos nacionales.
2. **Cierre Mensual y Ganancia/Pérdida en Cambio:**
   * Al conciliar facturas emitidas a una tasa $T_1$ con pagos recibidos a una tasa $T_2$, Odoo calcula y registra automáticamente la cuenta de **Diferencial Cambiario Realizado** (`4.2.01.xx Ganancia en Cambio` o `5.2.01.xx Pérdida en Cambio`).

---

## 16. Preguntas Frecuentes y Resolución de Incidencias Técnicas

### P: ¿Por qué una factura de compra no generó retención de IVA?
**R:** Verifique que:
1. La empresa tenga marcada la casilla *Contribuyente Especial* en su ficha.
2. El proveedor no esté marcado como *No Sujeto a Retención* (ej: Entidades del Estado o no domiciliados).
3. La factura tenga líneas con impuesto IVA (las compras 100% exentas no generan retención de IVA).

### P: ¿Cómo anular una factura fiscal emitida con error?
**R:** En la normativa venezolana, **las facturas con número de control no se eliminan**. Debe emitir una **Nota de Crédito Fiscal** vinculada a la factura original, la cual anulará el débito fiscal en el Libro de Ventas y reintegrará el inventario.

---
*Manual elaborado por el equipo de ingeniería para el ecosistema Odoo 19 Localización Venezuela.*
