"""Utilidades para validar y formatear RUT chileno."""


def limpiar_rut(rut: str) -> str:
    """Quitar puntos, guion y espacios; convertir K a mayúscula."""
    return rut.replace(".", "").replace("-", "").replace(" ", "").upper()


def calcular_dv(cuerpo: int | str) -> str:
    """Calcular dígito verificador (algoritmo módulo 11)."""
    nums = [int(d) for d in str(cuerpo)][::-1]
    weights = [2, 3, 4, 5, 6, 7]
    s = sum(n * weights[i % len(weights)] for i, n in enumerate(nums))
    mod = s % 11
    return "K" if mod == 1 else "0" if mod == 0 else str(11 - mod)


def validar_rut(rut: str) -> bool:
    """Verificar que el RUT tenga DV correcto."""
    limpio = limpiar_rut(rut)
    if not limpio or len(limpio) < 2:
        return False
    cuerpo = limpio[:-1]
    dv = limpio[-1]
    return cuerpo.isdigit() and calcular_dv(cuerpo) == dv


def formatear_rut(rut: str) -> str:
    """Dejando el RUT como XXX.XXX.XXX-DV."""
    limpio = limpiar_rut(rut)
    cuerpo = limpio[:-1]
    dv = limpio[-1:] if len(limpio) > 0 else ""
    parts = []
    for i in range(len(cuerpo), 0, -3):
        start = max(0, i - 3)
        parts.append(cuerpo[start:i])
    fmt = ".".join(reversed(parts))
    return f"{fmt}-{dv}"
