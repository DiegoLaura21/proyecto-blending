"""Carga del escenario, optimización y controles de balance para blending de cobre."""

from dataclasses import dataclass
from datetime import date
import json
from math import ceil, floor, isfinite
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


@dataclass(frozen=True)
class Ruma:
    id: str
    nombre: str
    stock_tmh: float
    cu_pct: float
    humedad_pct: float
    incertidumbre_pp: float
    retiro_max_tmh_dia: float
    ciclo_min: float


@dataclass(frozen=True)
class Dia:
    fecha: str
    planta_tmh: float
    tolerancia_tmh: float
    camiones: int
    horas_efectivas: float

    @property
    def minutos_flota(self):
        return self.camiones * self.horas_efectivas * 60


@dataclass(frozen=True)
class Escenario:
    mina: str
    ley_min_cu_pct: float
    ley_objetivo_cu_pct: float
    ley_max_cu_pct: float
    tolerancia_objetivo_pp: float
    payload_tmh: float
    penalizacion_min_por_t_cu: float
    tiempo_limite_s: float
    rumas: tuple[Ruma, ...]
    dias: tuple[Dia, ...]

    @property
    def corredor_objetivo(self):
        return (
            self.ley_objetivo_cu_pct - self.tolerancia_objetivo_pp,
            self.ley_objetivo_cu_pct + self.tolerancia_objetivo_pp,
        )


@dataclass(frozen=True)
class Plan:
    viajes: np.ndarray
    estado: str
    brecha_relativa: float | None
    objetivo_equivalente_min: float


def numero(valor, campo):
    if type(valor) not in (int, float) or not isfinite(valor):
        raise ValueError(f"{campo} debe ser un número finito.")
    return valor


def etiqueta(valor, campo):
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{campo} debe ser texto no vacío.")


def cargar_escenario(ruta: Path) -> Escenario:
    with ruta.open(encoding="utf-8-sig") as archivo:
        datos = json.load(archivo)
    if not isinstance(datos, dict):
        raise ValueError("El escenario JSON debe ser un objeto.")
    try:
        rumas = tuple(Ruma(**fila) for fila in datos["rumas"])
        dias = tuple(Dia(**fila) for fila in datos["dias"])
        escenario = Escenario(**{**datos, "rumas": rumas, "dias": dias})
    except (KeyError, TypeError) as error:
        raise ValueError(f"Estructura de escenario incorrecta. {error}") from error
    validar_escenario(escenario)
    return escenario


def validar_escenario(e):
    etiqueta(e.mina, "mina")
    for campo in (
        "ley_min_cu_pct", "ley_objetivo_cu_pct", "ley_max_cu_pct",
        "tolerancia_objetivo_pp", "payload_tmh", "penalizacion_min_por_t_cu", "tiempo_limite_s",
    ):
        numero(getattr(e, campo), campo)
    if not 0 <= e.ley_min_cu_pct < e.ley_objetivo_cu_pct < e.ley_max_cu_pct <= 100:
        raise ValueError("Las leyes deben cumplir 0 ≤ mínimo < objetivo < máximo ≤ 100.")
    bajo, alto = e.corredor_objetivo
    if e.tolerancia_objetivo_pp < 0 or bajo < e.ley_min_cu_pct or alto > e.ley_max_cu_pct:
        raise ValueError("El corredor objetivo debe quedar dentro de la banda de planta.")
    if min(e.payload_tmh, e.penalizacion_min_por_t_cu, e.tiempo_limite_s) <= 0:
        raise ValueError("El payload, la penalización de ley y el tiempo límite deben ser positivos.")
    if not e.rumas or not e.dias:
        raise ValueError("Se requiere al menos una ruma y un día.")

    for r in e.rumas:
        etiqueta(r.id, "ID de ruma")
        etiqueta(r.nombre, f"Nombre de {r.id}")
        for campo in ("stock_tmh", "cu_pct", "humedad_pct", "incertidumbre_pp",
                      "retiro_max_tmh_dia", "ciclo_min"):
            numero(getattr(r, campo), f"{r.id}.{campo}")
        if min(r.stock_tmh, r.retiro_max_tmh_dia) < 0 or r.ciclo_min <= 0:
            raise ValueError(f"{r.id}: stock y retiro no negativos, y ciclo positivo.")
        if not 0 <= r.humedad_pct < 100 or not 0 <= r.cu_pct <= 100 or r.incertidumbre_pp < 0:
            raise ValueError(f"{r.id}: revisa humedad, ley de Cu e incertidumbre.")
    if len({r.id for r in e.rumas}) != len(e.rumas):
        raise ValueError("Los ID de las rumas deben ser únicos.")

    fechas = []
    for d in e.dias:
        etiqueta(d.fecha, "fecha")
        fecha = date.fromisoformat(d.fecha)
        if fecha.isoformat() != d.fecha:
            raise ValueError("Usa fechas en formato AAAA-MM-DD.")
        fechas.append(fecha)
        for campo in ("planta_tmh", "tolerancia_tmh", "horas_efectivas"):
            numero(getattr(d, campo), f"{d.fecha}.{campo}")
        if d.planta_tmh <= 0 or not 0 <= d.tolerancia_tmh < d.planta_tmh:
            raise ValueError(f"{d.fecha}: revisa el tonelaje objetivo y su tolerancia.")
        if type(d.camiones) is not int or d.camiones < 1 or not 0 < d.horas_efectivas <= 24:
            raise ValueError(f"{d.fecha}: se requieren camiones enteros y hasta 24 h efectivas.")
    if fechas != sorted(set(fechas)):
        raise ValueError("Las fechas deben estar ordenadas y sin duplicados.")


def insumos_por_viaje(e):
    seca = e.payload_tmh * (1 - np.array([r.humedad_pct for r in e.rumas]) / 100)
    ley = np.array([r.cu_pct for r in e.rumas])
    incertidumbre = np.array([r.incertidumbre_pp for r in e.rumas])
    return seca, ley, np.maximum(0, ley - incertidumbre), np.minimum(100, ley + incertidumbre)


def optimizar(e: Escenario) -> Plan:
    """Minimiza minutos de acarreo y penalizaciones, con calidad diaria como restricción dura."""
    nd, nr = len(e.dias), len(e.rumas)
    n_viajes = nd * nr
    n_variables = n_viajes + 2 * nd  # Exceso equivalente de Cu y desviación de tonelaje.
    n_filas = nr + 8 * nd
    matriz = lil_matrix((n_filas, n_variables), dtype=float)
    inferior = np.full(n_filas, -np.inf)
    superior = np.full(n_filas, np.inf)
    max_retiro = np.array([floor(r.retiro_max_tmh_dia / e.payload_tmh + 1e-9) for r in e.rumas])
    max_stock = np.array([floor(r.stock_tmh / e.payload_tmh + 1e-9) for r in e.rumas])
    ciclos = np.array([r.ciclo_min for r in e.rumas])
    seca, nominal, baja, alta = insumos_por_viaje(e)
    objetivo_bajo, objetivo_alto = e.corredor_objetivo

    for r, stock in enumerate(max_stock):
        matriz[r, r:n_viajes:nr] = 1
        superior[r] = stock
    minimo_total = 0
    for i, dia in enumerate(e.dias):
        fila = nr + 8 * i
        bloque = slice(i * nr, (i + 1) * nr)
        minimo = ceil((dia.planta_tmh - dia.tolerancia_tmh) / e.payload_tmh - 1e-9)
        maximo = floor((dia.planta_tmh + dia.tolerancia_tmh) / e.payload_tmh + 1e-9)
        if minimo > maximo:
            raise ValueError(f"{dia.fecha}: el rango a planta no admite un número entero de viajes de "
                             f"{e.payload_tmh:g} TMH. Ajusta el tonelaje o tolerancia.")
        if minimo > min(np.minimum(max_retiro, max_stock).sum(), floor(dia.minutos_flota / ciclos.min())):
            raise ValueError(f"{dia.fecha}: la capacidad de retiro, stock o flota no cubre el mínimo de viajes.")
        minimo_total += minimo
        matriz[fila, bloque] = 1
        inferior[fila], superior[fila] = minimo, maximo
        matriz[fila + 1, bloque] = ciclos
        superior[fila + 1] = dia.minutos_flota

        # Cada producto de ley (%)/100 por masa seca da toneladas de Cu.
        matriz[fila + 2, bloque] = seca * (baja - e.ley_min_cu_pct) / 100
        inferior[fila + 2] = 0
        matriz[fila + 3, bloque] = seca * (alta - e.ley_max_cu_pct) / 100
        superior[fila + 3] = 0
        matriz[fila + 4, bloque] = seca * (objetivo_bajo - nominal) / 100
        matriz[fila + 5, bloque] = seca * (nominal - objetivo_alto) / 100
        matriz[fila + 4:fila + 6, n_viajes + i] = -1
        superior[fila + 4:fila + 6] = 0

        matriz[fila + 6, bloque] = 1
        matriz[fila + 7, bloque] = -1
        matriz[fila + 6:fila + 8, n_viajes + nd + i] = -1
        viajes_objetivo = dia.planta_tmh / e.payload_tmh
        superior[fila + 6:fila + 8] = [viajes_objetivo, -viajes_objetivo]

    if minimo_total > max_stock.sum():
        raise ValueError("El stock inicial de viajes completos no cubre el tonelaje mínimo del horizonte.")

    costo = np.r_[np.tile(ciclos, nd), np.full(nd, e.penalizacion_min_por_t_cu), np.full(nd, 1000)]
    integridad = np.r_[np.ones(n_viajes), np.zeros(2 * nd)]
    max_variables = np.r_[np.tile(np.minimum(max_stock, max_retiro), nd), np.full(2 * nd, np.inf)]
    solucion = milp(
        c=costo, integrality=integridad, bounds=Bounds(0, max_variables),
        constraints=LinearConstraint(matriz.tocsc(), inferior, superior),
        options={"time_limit": e.tiempo_limite_s, "mip_rel_gap": 0.001},
    )
    if solucion.status == 2:
        raise ValueError("No existe un plan factible para la combinación de leyes, flota, retiros, "
                         "inventario y tonelajes. Revisa los límites o incorpora stock compatible.")
    if solucion.status not in (0, 1) or solucion.x is None:
        raise ValueError(f"El optimizador no encontró un plan verificable. {solucion.message}")
    fraccion = solucion.x[:n_viajes].reshape(nd, nr)
    viajes = np.rint(fraccion).astype(int)
    if not np.allclose(fraccion, viajes, rtol=0, atol=1e-5):
        raise ValueError("El optimizador devolvió viajes fuera de la tolerancia de integridad.")
    verificar_plan(e, viajes)
    estado = "optimizado" if solucion.status == 0 else "factible_con_limite"
    return Plan(viajes, estado, getattr(solucion, "mip_gap", None), float(solucion.fun))


def verificar_plan(e, viajes):
    """Comprueba las restricciones sobre los viajes enteros que salen del programa."""
    seca, _, baja, alta = insumos_por_viaje(e)
    eps = 1e-6
    if (viajes < 0).any() or (viajes.sum(axis=0) * e.payload_tmh >
                             np.array([r.stock_tmh for r in e.rumas]) + eps).any():
        raise ValueError("El plan incumple los límites de stock.")
    if (viajes * e.payload_tmh > np.array([r.retiro_max_tmh_dia for r in e.rumas]) + eps).any():
        raise ValueError("El plan sobrepasa el máximo de retiro por ruma.")
    for d, asignacion in zip(e.dias, viajes):
        tmh = asignacion.sum() * e.payload_tmh
        minutos = asignacion @ np.array([r.ciclo_min for r in e.rumas])
        tms = asignacion @ seca
        if tms <= 0 or abs(tmh - d.planta_tmh) > d.tolerancia_tmh + eps or minutos > d.minutos_flota + eps:
            raise ValueError(f"{d.fecha}: el plan incumple tonelaje o capacidad de flota.")
        if (asignacion @ (seca * baja) / tms < e.ley_min_cu_pct - eps or
                asignacion @ (seca * alta) / tms > e.ley_max_cu_pct + eps):
            raise ValueError(f"{d.fecha}: el plan incumple la banda de ley con incertidumbre.")

