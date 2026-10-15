"""Validador de RUT chileno."""


def limpiar_rut(rut: str) -> str:
    """Quita puntos, guion y espacios; deja solo dígitos y posible 'K'."""
    return rut.replace(".", "").replace("-", "").strip().upper()


def calcular_dv(cuerpo: str | int) -> str:
    """Calcula dígito verificador de un RUT usando el algoritmo M10."""
    n = int(cuerpo)
    multiplicadores = [2, 3, 4, 5, 6, 7]
    digits = [int(d) for d in str(n)][::-1]
    suma = sum(d * multiplicadores[i % len(multiplicadores)] for i, d in enumerate(digits))
    dv = 11 - (suma % 11)
    if dv == 11:
        return "0"
    if dv == 10:
        return "K"
    return str(dv)


def validar_rut(rut: str) -> bool:
    """Devuelve True si el RUT es válido."""
    if not rut:
        return False
    limpio = limpiar_rut(rut)
    if not limpio.isdigit() and not (limpio[:-1].isdigit() and limpio[-1] == "K"):
        return False
    if not limpio[:-1]:
        return False
    return calcular_dv(limpio[:-1]) == limpio[-1]


def formatear_rut(rut: str) -> str:
    """Formatea un RUT como xx.xxx.xx-dv."""
    limpio = limpiar_rut(rut)
    if limpio[-1] == "K":
        cuerpo = limpio[:-1]
        dv = "K"
    else:
        cuerpo = limpio[:-1]
        dv = limpio[-1]
    formateado = f"{int(cuerpo):,}".replace(",", ".")
    return f"{formateado}-{dv}"


def generar_rut(cuerpo: int) -> str:
    """Genera un RUT formateado a partir de su cuerpo numérico."""
    dv = calcular_dv(cuerpo)
    formateado = f"{cuerpo:,}".replace(",", ".")
    return f"{formateado}-{dv}"


def rut_a_tupla(rut: str) -> tuple[int, str]:
    """Convierte un RUT formateado en (cuerpo_int, dv)."""
    limpio = limpiar_rut(rut)
    if not limpio[:-1].isdigit():
        raise ValueError(f"RUT inválido: {rut}")
    dv_esperado = calcular_dv(limpio[:-1])
    if dv_esperado != limpio[-1]:
        raise ValueError(f"RUT inválido: {rut}")
    return (int(limpio[:-1]), limpio[-1])
