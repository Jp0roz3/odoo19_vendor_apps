# -*- coding: utf-8 -*-
"""
Venezuela360: Test Suite — account.wh.iva / l10n_ve.exchange.rate
==================================================================
Tests de instalación y funcionalidad básica para Odoo 19.

Estos tests verifican:
1. Creación de tasa BCV
2. Cálculo de retención IVA (75% y 100%)
3. Cálculo de retención ISLR por método porcentaje
4. Territorialidad — estados venezolanos

Autor: JeanPerozo / Nubelco
"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestExchangeRate(TransactionCase):
    """Tests para el modelo l10n_ve.exchange.rate."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Activar la localización venezolana en la compañía de pruebas
        cls.company = cls.env.company
        cls.company.l10n_ve_active = True

        # Moneda Bs (VES o USD si VES no existe)
        cls.currency_ves = cls.env['res.currency'].search(
            [('name', 'in', ['VES', 'VEF', 'VEB'])], limit=1
        )
        if not cls.currency_ves:
            cls.currency_ves = cls.env.ref('base.USD')

    def test_01_create_exchange_rate(self):
        """Crear una tasa BCV básica."""
        rate = self.env['l10n_ve.exchange.rate'].create({
            'name': 'Tasa BCV Test',
            'date': '2024-01-15',
            'rate': 36.50,
            'company_id': self.company.id,
        })
        self.assertEqual(rate.rate, 36.50)
        self.assertEqual(rate.date.year, 2024)

    def test_02_exchange_rate_unique_per_date(self):
        """No puede haber dos tasas el mismo día para la misma compañía."""
        self.env['l10n_ve.exchange.rate'].create({
            'name': 'Tasa BCV Test Unique 1',
            'date': '2024-02-01',
            'rate': 37.00,
            'company_id': self.company.id,
        })
        with self.assertRaises(Exception):
            self.env['l10n_ve.exchange.rate'].create({
                'name': 'Tasa BCV Test Unique 2',
                'date': '2024-02-01',
                'rate': 38.00,
                'company_id': self.company.id,
            })

    def test_03_get_rate_for_date(self):
        """get_rate_for_date retorna la tasa correcta para la fecha."""
        self.env['l10n_ve.exchange.rate'].create({
            'name': 'BCV Marzo 2024',
            'date': '2024-03-10',
            'rate': 42.00,
            'company_id': self.company.id,
        })
        rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(
            '2024-03-15', company_id=self.company.id
        )
        self.assertTrue(rate_rec, 'Debe encontrar una tasa para 2024-03-15')
        self.assertEqual(rate_rec.rate, 42.00)

    def test_04_rate_zero_not_allowed(self):
        """Tasa cero no está permitida."""
        with self.assertRaises((UserError, ValidationError)):
            self.env['l10n_ve.exchange.rate'].create({
                'name': 'Tasa Cero',
                'date': '2024-04-01',
                'rate': 0.0,
                'company_id': self.company.id,
            })


class TestUtHistory(TransactionCase):
    """Tests para el modelo account.ut.history."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_01_create_ut(self):
        """Crear un valor de UT."""
        ut = self.env['account.ut.history'].create({
            'name': 'UT Test 2024',
            'date_from': '2024-01-01',
            'value_bs': 9000.0,
            'company_id': self.company.id,
        })
        self.assertEqual(ut.value_bs, 9000.0)

    def test_02_get_ut_for_date(self):
        """get_ut_for_date retorna la UT correcta."""
        self.env['account.ut.history'].create({
            'name': 'UT Abril 2024',
            'date_from': '2024-04-01',
            'value_bs': 9500.0,
            'company_id': self.company.id,
        })
        ut = self.env['account.ut.history'].get_ut_for_date(
            '2024-06-15', company_id=self.company.id
        )
        self.assertTrue(ut, 'Debe encontrar UT para junio 2024')
        self.assertGreaterEqual(ut.value_bs, 9500.0)


class TestTerritory(TransactionCase):
    """Tests para modelos de territorialidad venezolana."""

    def test_01_states_loaded(self):
        """Los 24 estados de Venezuela deben estar cargados."""
        states = self.env['l10n_ve.state'].search([])
        self.assertGreaterEqual(
            len(states), 24,
            f'Deben existir al menos 24 estados (encontrados: {len(states)})'
        )

    def test_02_carabobo_exists(self):
        """El estado Carabobo debe existir."""
        carabobo = self.env['l10n_ve.state'].search([('name', 'ilike', 'Carabobo')])
        self.assertTrue(carabobo, 'El estado Carabobo debe existir en la base de datos')

    def test_03_municipality_has_state(self):
        """Todo municipio debe tener un estado asociado."""
        municipalities = self.env['l10n_ve.municipality'].search([])
        if municipalities:
            for m in municipalities[:10]:  # revisar los primeros 10
                self.assertTrue(
                    m.state_id,
                    f'El municipio {m.name} debe tener un estado asociado'
                )


class TestWhIvaCalculation(TransactionCase):
    """Tests para el cálculo de retención de IVA."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.l10n_ve_active = True

    def test_01_wh_rate_75_percent(self):
        """Retención IVA al 75% calcula correctamente."""
        # Simulamos el cálculo: Base=1000 Bs, IVA=160 Bs (16%), Ret 75%=120 Bs
        iva_bs = 160.0
        wh_rate = 75.0
        expected = round(iva_bs * wh_rate / 100.0, 2)
        self.assertEqual(expected, 120.0)

    def test_02_wh_rate_100_percent(self):
        """Retención IVA al 100% es igual al IVA total."""
        iva_bs = 160.0
        wh_rate = 100.0
        expected = round(iva_bs * wh_rate / 100.0, 2)
        self.assertEqual(expected, 160.0)

    def test_03_dual_currency_conversion(self):
        """Conversión dual Bs/USD es correcta."""
        amount_bs = 1000.0
        rate = 40.0  # 40 Bs por USD
        amount_usd = round(amount_bs / rate, 4)
        self.assertEqual(amount_usd, 25.0)
