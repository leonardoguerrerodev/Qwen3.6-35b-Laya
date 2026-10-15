"""Validador de RUT chileno — solo biblioteca estándar."""


def limpiar_rut(rut: str) -> str:
    """Quita puntos, guion y espacios; convierte K a mayúscula."""
    limpio = rut.replace(".", "").replace("-", "").replace(" ", "")
    return limpio.upper()


def calcular_dv(cuerpo) -> str:
    """Calcula dígito verificador usando el algoritmo módulo 11."""
    n = int(str(cuerpo))
    multiplicadores = [2, 3, 4, 5, 6, 7]
    digits = [int(d) for d in str(n)]
    rev_digits = list(reversed(digits))
    suma = sum(d * multiplicadores[i % len(multiplicadores)]
               for i, d in enumerate(rev_digits))
    resto = suma % 11
    dv = 11 - resto
    return "K" if dv == 10 else str(dv) if dv != 11 else "0"


def validar_rut(rut: str) -> bool:
    """Devuelve True si el RUT es válido, False en caso contrario."""
    limpio = limpiar_rut(rut)
    if not limpio:
        return False
    try:
        dv_calculado = calcular_dv(limpio[:-1])
    except (ValueError, IndexError):
        return False
    return limpio[-1] == dv_calculado


def formatear_rut(rut: str) -> str:
    """Devuelve el RUT formateado como XX.XXX.XXX-D."""
    limpio = limpiar_rut(rut)
    cuerpo = limpio[:-1] if len(limpio) > 1 else limpio
    dv = limpio[-1] if len(limpio) > 1 else ""
    # Insertar puntos cada 3 dígitos desde la derecha
    formateado = ""
    for i, d in enumerate(reversed(cuerpo)):
        if i > 0 and i % 3 == 0:
            formateado = "." + formateado
        formateado = d + formateado
    if dv:
        formateado = formateado + "-" + dv
    return formateado


def generar_rut(cuerpo) -> str:
    """Genera un RUT formateado a partir de un número entero."""
    dv = calcular_dv(cuerpo)
    cuerpo_str = str(cuerpo)
    formateado = ""
    for i, d in enumerate(reversed(cuerpo_str)):
        if i > 0 and i % 3 == 0:
            formateado = "." + formateado
        formateado = d + formateado
    return formateado + "-" + dv


def rut_a_tupla(rut: str) -> tuple:
    """Convierte un RUT formateado en (número, dv); lanza ValueError si es inválido."""
    if not validar_rut(rut):
        raise ValueError(f"RUT inválido: {rut}")
    limpio = limpiar_rut(rut)
    return (int(limpio[:-1]), limpio[-1])
