import unittest
from rut import limpiar_rut, calcular_dv, validar_rut, formatear_rut


class TestLimpiar(unittest.TestCase):
    def test_quita_puntos_y_guion(self):
        self.assertEqual(limpiar_rut("12.345.678-5"), "123456785")

    def test_k_minuscula_y_espacios(self):
        self.assertEqual(limpiar_rut(" 16666666-k "), "16666666K")

    def test_vacio(self):
        self.assertEqual(limpiar_rut(""), "")


class TestDV(unittest.TestCase):
    def test_casos_normales(self):
        self.assertEqual(calcular_dv(12345678), "5")
        self.assertEqual(calcular_dv(11111111), "1")
        self.assertEqual(calcular_dv(7777777), "6")

    def test_k_y_cero(self):
        self.assertEqual(calcular_dv(16666666), "K")
        self.assertEqual(calcular_dv(6), "K")
        self.assertEqual(calcular_dv(1000013), "0")

    def test_acepta_texto(self):
        self.assertEqual(calcular_dv("12345678"), "5")


class TestValidar(unittest.TestCase):
    def test_validos(self):
        self.assertTrue(validar_rut("12.345.678-5"))
        self.assertTrue(validar_rut("12345678-5"))
        self.assertTrue(validar_rut("18.972.631-7"))
        self.assertTrue(validar_rut("16.666.666-k"))
        self.assertTrue(validar_rut("1-9"))

    def test_invalidos(self):
        self.assertFalse(validar_rut("12.345.678-9"))
        self.assertFalse(validar_rut(""))
        self.assertFalse(validar_rut("abc"))
        self.assertFalse(validar_rut("5"))


class TestFormatear(unittest.TestCase):
    def test_con_puntos_y_guion(self):
        self.assertEqual(formatear_rut("123456785"), "12.345.678-5")
        self.assertEqual(formatear_rut("12345678-5"), "12.345.678-5")

    def test_cuerpo_corto_y_k(self):
        self.assertEqual(formatear_rut("19"), "1-9")
        self.assertEqual(formatear_rut("16666666k"), "16.666.666-K")


if __name__ == "__main__":
    unittest.main()
