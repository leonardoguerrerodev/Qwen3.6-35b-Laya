"""Validador de RUT chileno."""


def limpiar_rut(s: str) -> str:
    """Quitar puntos, guion y espacios; dejar cuerpo en mayúsculas."""
    return s.replace(".", "").replace("-", "").strip().upper()


def calcular_dv(cuerpo: int | str) -> str:
    """Calcular dígito verificador del RUT (algoritmo módulo 11)."""
    n = int(cuerpo)
    factor = 2
    suma = 0
    while n > 0:
        suma += (n % 10) * factor
        n //= 10
        factor += 1
        if factor > 7:
            factor = 2
    dv_num = 11 - (suma % 11)
    if dv_num == 11:
        return "0"
    if dv_num == 10:
        return "K"
    return str(dv_num)


def validar_rut(s: str) -> bool:
    """Verificar que el RUT tenga formato correcto y DV válido."""
    if not s or not s.strip():
        return False
    # debe tener al menos un guion
    if "-" not in s:
        return False
    # limpiar solo puntos y espacios, conservar guion para el split
    limpio = s.replace(".", "").replace(" ", "").strip().upper()
    partes = limpio.split("-", 1)
    if len(partes) != 2:
        return False
    cuerpo, dv = partes
    if not cuerpo or not dv:
        return False
    if not cuerpo.isdigit() or dv not in ("0", "1", "2", "3", "4", "5",
                                          "6", "7", "8", "9", "K"):
        return False
    return calcular_dv(cuerpo) == dv


def formatear_rut(s: str) -> str:
    """Formatear un RUT limpio como 12.345.678-9."""
    limpio = limpiar_rut(s)
    if "-" in limpio:
        limpio = limpio.replace("-", "")
    cuerpo = limpio[:-1]
    dv = limpio[-1]
    # Insertar puntos desde la derecha: cada 3 dígitos
    partes = []
    while len(cuerpo) > 3:
        partes.append(cuerpo[-3:])
        cuerpo = cuerpo[:-3]
    partes.append(cuerpo)
    partes.reverse()
    return f"{'.'.join(partes)}-{dv}"


def generar_rut(cuerpo: int) -> str:
    """Generar RUT formateado a partir de un cuerpo numérico."""
    dv = calcular_dv(cuerpo)
    return formatear_rut(f"{cuerpo}{dv}")


def rut_a_tupla(s: str) -> tuple[int, str]:
    """Convertir RUT formateado a (cuerpo_int, dv). Valida el DV."""
    if not validar_rut(s):
        raise ValueError(f"RUT inválido: {s}")
    limpio = s.replace(".", "").replace(" ", "").strip().upper()
    cuerpo, dv = limpio.split("-", 1)
    return (int(cuerpo), dv)
