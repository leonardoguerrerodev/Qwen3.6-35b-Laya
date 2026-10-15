import unittest
from rut import generar_rut, rut_a_tupla


class TestExtra(unittest.TestCase):
    def test_generar_rut(self):
        self.assertEqual(generar_rut(12345678), "12.345.678-5")
        self.assertEqual(generar_rut(6), "6-K")

    def test_rut_a_tupla(self):
        self.assertEqual(rut_a_tupla("12.345.678-5"), (12345678, "5"))
        self.assertEqual(rut_a_tupla("16.666.666-k"), (16666666, "K"))

    def test_rut_a_tupla_invalido(self):
        with self.assertRaises(ValueError):
            rut_a_tupla("12.345.678-9")


if __name__ == "__main__":
    unittest.main()
