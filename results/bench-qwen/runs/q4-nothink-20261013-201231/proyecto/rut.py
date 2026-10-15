"""Validador de RUT chileno (solo biblioteca estándar)."""


def limpiar_rut(rut: str) -> str:
    """Quitar puntos y guion, devolver cuerpo+dV en mayúsculas."""
    return rut.replace(".", "").replace("-", "").strip().upper()


def calcular_dv(cuerpo: str | int) -> str:
    """Calcular dígito verificador del algoritmo módulo 11."""
    digits = [int(d) for d in str(cuerpo)][::-1]
    multiplicadores = [2, 3, 4, 5, 6, 7] * 3
    total = sum(d * m for d, m in zip(digits, multiplicadores))
    dv_num = 11 - (total % 11)
    if dv_num == 11:
        return "0"
    if dv_num == 10:
        return "K"
    return str(dv_num)


def validar_rut(rut: str) -> bool:
    """Devolver True si el RUT es válido (formato + DV correcto)."""
    if not rut or not rut.strip():
        return False
    limpio = limpiar_rut(rut)
    if not limpio:
        return False
    cuerpo = limpio[:-1]
    dv = limpio[-1]
    if not cuerpo.isdigit():
        return False
    if dv not in "0123456789K":
        return False
    return calcular_dv(cuerpo) == dv


def formatear_rut(rut: str) -> str:
    """Devolver RUT con formato 12.345.678-9."""
    limpio = limpiar_rut(rut)
    cuerpo = limpio[:-1]
    dv = limpio[-1]
    cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".")
    return f"{cuerpo_formateado}-{dv}"


def generar_rut(cuerpo: int) -> str:
    """Generar RUT formateado a partir de un cuerpo numérico."""
    dv = calcular_dv(cuerpo)
    cuerpo_formateado = f"{cuerpo:,}".replace(",", ".")
    return f"{cuerpo_formateado}-{dv}"


def rut_a_tupla(rut: str) -> tuple[int, str]:
    """Convertir RUT formateado a (cuerpo_int, dv). Levanta ValueError si inválido."""
    if not validar_rut(rut):
        raise ValueError(f"RUT inválido: {rut}")
    limpio = limpiar_rut(rut)
    return (int(limpio[:-1]), limpio[-1])
