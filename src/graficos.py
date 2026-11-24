"""Figuras del plan de alimentación, ley y disponibilidad de rumas."""

from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np


TINTA = "#1d3131"
VERDE = "#13765c"
OCRE = "#b45f36"
PALETA = ["#496e8b", "#479694", "#794f83", "#b76b47", "#a5812d", "#287851"]


def configurar_estilo():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "figure.facecolor": "#f3f6f3",
        "axes.facecolor": "white", "text.color": TINTA, "axes.labelcolor": TINTA,
        "axes.edgecolor": "#c0ccc5", "axes.spines.top": False, "axes.spines.right": False,
        "axes.axisbelow": True, "grid.color": "#e0e9e3", "legend.frameon": False,
        "savefig.dpi": 155, "axes.unicode_minus": False,
    })


def formatear(decimales):
    return FuncFormatter(
        lambda valor, _: f"{valor:,.{decimales}f}".replace(",", " ").replace(".", ",")
    )


def figura(e, titulo, subtitulo, altura=5.2, ejes=1):
    fig, ax = plt.subplots(ejes, 1, figsize=(11.3, altura), sharex=ejes > 1, squeeze=False)
    fig.subplots_adjust(left=0.11, right=0.95, top=0.76 if ejes == 1 else 0.80,
                        bottom=0.18, hspace=0.32)
    fig.text(0.11, 0.945, titulo, fontsize=23, fontweight="bold", va="top")
    fig.text(0.111, 0.865 if ejes == 1 else 0.885,
             f"{e.mina} · {subtitulo} · Datos sintéticos", color="#4d665f", va="top")
    for eje in ax[:, 0]:
        eje.grid(axis="y", linewidth=0.8)
    return fig, ax[:, 0]


def eje_fechas(ax, fechas):
    if len(fechas) <= 12:
        ax.set_xticks(fechas)
    else:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=9))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.set_xlabel("Fecha de alimentación")


def guardar(fig, ruta):
    fig.savefig(ruta, facecolor=fig.get_facecolor())
    plt.close(fig)


def graficar(e, viajes, diarios, salida):
    configurar_estilo()
    fechas = [date.fromisoformat(d.fecha) for d in e.dias]
    colores = [PALETA[i % len(PALETA)] for i in range(len(e.rumas))]
    etiquetas = [r.id for r in e.rumas]
    nominal = np.array([d["ley_cu_pct"] for d in diarios])
    limite_bajo = np.array([d["ley_inferior_cu_pct"] for d in diarios])
    limite_alto = np.array([d["ley_superior_cu_pct"] for d in diarios])

    fig, (ax,) = figura(e, "Ley diaria de alimentación", "Ley de Cu ponderada por masa seca")
    banda = ax.axhspan(e.ley_min_cu_pct, e.ley_max_cu_pct, color="#dbece4", label="Banda de planta")
    meta = ax.axhline(e.ley_objetivo_cu_pct, color=OCRE, linestyle="--", label="Ley objetivo")
    nominal_trazo = ax.errorbar(
        fechas, nominal, yerr=[nominal - limite_bajo, limite_alto - nominal],
        marker="o", color=VERDE, ecolor="#498780", capsize=5, linewidth=2,
        label="Ley nominal e intervalo por incertidumbre",
    )
    margen = 0.12 * (e.ley_max_cu_pct - e.ley_min_cu_pct)
    ax.set_ylim(max(0, e.ley_min_cu_pct - margen), min(100, e.ley_max_cu_pct + margen))
    ax.set_ylabel("Ley de Cu (%)")
    ax.yaxis.set_major_formatter(formatear(3))
    eje_fechas(ax, fechas)
    fig.legend(handles=[banda, meta, nominal_trazo], loc="lower center", ncols=3, bbox_to_anchor=(0.52, 0.025))
    guardar(fig, salida / "01_ley_diaria.png")

    fig, (ax, flota) = figura(e, "Retiro de rumas y uso de flota", "Carga diaria a chancado", altura=7.1, ejes=2)
    base = np.zeros(len(fechas))
    for etiqueta, viajes_ruma, color in zip(etiquetas, viajes.T, colores):
        masa = viajes_ruma * e.payload_tmh
        ax.bar(fechas, masa, bottom=base, color=color, label=etiqueta, width=0.76)
        base += masa
    ax.plot(fechas, [d.planta_tmh for d in e.dias], color=TINTA, marker="D", markersize=4,
            linestyle="--", label="Meta de planta")
    ax.set_ylabel("Alimentación (TMH)")
    ax.yaxis.set_major_formatter(formatear(0))
    flota.bar(fechas, [d["uso_flota_pct"] for d in diarios], color="#519183", width=0.70)
    flota.axhline(100, color=OCRE, linestyle="--", linewidth=1.3)
    flota.set_ylabel("Uso de minutos\nde flota (%)")
    flota.set_ylim(0, 108)
    eje_fechas(flota, fechas)
    fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncols=min(7, len(etiquetas) + 1),
               bbox_to_anchor=(0.52, 0.031))
    guardar(fig, salida / "02_retiro_y_flota.png")

    fig, (ax,) = figura(e, "Balance de inventario por ruma", "Stock sin reposición durante el horizonte")
    retiros = viajes.sum(axis=0) * e.payload_tmh
    saldo = np.array([r.stock_tmh for r in e.rumas]) - retiros
    posiciones = np.arange(len(etiquetas))
    ax.barh(posiciones, retiros, color=colores)
    ax.barh(posiciones, saldo, left=retiros, color="#dce7df")
    ax.set_yticks(posiciones, [f"{r.id} · {r.nombre}" for r in e.rumas])
    ax.invert_yaxis()
    ax.grid(axis="x", linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(formatear(0))
    ax.set_xlabel("Inventario inicial distribuido entre retiro y saldo (TMH)")
    fig.subplots_adjust(left=0.23)
    fig.legend(handles=[Patch(facecolor=VERDE, label="Retirado (color de ruma)"),
                        Patch(facecolor="#dce7df", label="Saldo final")],
               ncols=2, loc="lower center", bbox_to_anchor=(0.55, 0.025))
    guardar(fig, salida / "03_inventario.png")

