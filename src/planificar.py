"""Genera un plan diario de blending desde un escenario JSON."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from graficos import graficar
from modelo import cargar_escenario, insumos_por_viaje, optimizar


RAIZ = Path(__file__).resolve().parents[1]


def tabular(e, plan):
    seca, nominal, baja, alta = insumos_por_viaje(e)
    stocks = np.array([r.stock_tmh for r in e.rumas], dtype=float)
    diarios, detalle = [], []
    for d, viajes in zip(e.dias, plan.viajes):
        tmh = viajes * e.payload_tmh
        tms = viajes * seca
        cobre = tms * nominal / 100
        minutos = viajes * [r.ciclo_min for r in e.rumas]
        tms_total = float(tms.sum())
        diarios.append({
            "fecha": d.fecha,
            "objetivo_tmh": d.planta_tmh,
            "alimentacion_tmh": float(tmh.sum()),
            "desviacion_tmh": float(tmh.sum() - d.planta_tmh),
            "alimentacion_tms": tms_total,
            "cu_contenido_t": float(cobre.sum()),
            "ley_cu_pct": float(100 * cobre.sum() / tms_total),
            "ley_inferior_cu_pct": float(tms @ baja / tms_total),
            "ley_superior_cu_pct": float(tms @ alta / tms_total),
            "viajes": int(viajes.sum()),
            "camiones_asignados": d.camiones,
            "minutos_flota_usados": float(minutos.sum()),
            "minutos_flota_disponibles": d.minutos_flota,
            "uso_flota_pct": float(100 * minutos.sum() / d.minutos_flota),
        })
        for j, r in enumerate(e.rumas):
            detalle.append({
                "fecha": d.fecha,
                "ruma": r.id,
                "nombre": r.nombre,
                "viajes": int(viajes[j]),
                "stock_inicio_tmh": float(stocks[j]),
                "retiro_tmh": float(tmh[j]),
                "retiro_tms": float(tms[j]),
                "cu_pct": r.cu_pct,
                "cu_contenido_t": float(cobre[j]),
                "stock_final_tmh": float(stocks[j] - tmh[j]),
                "ciclo_min": r.ciclo_min,
                "minutos_flota_usados": float(minutos[j]),
            })
        stocks -= tmh

    return diarios, detalle


def escribir_csv(ruta, filas):
    with ruta.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        escritor.writeheader()
        for fila in filas:
            escritor.writerow({k: f"{v:.6f}" if isinstance(v, float) else v for k, v in fila.items()})


def ejecutar(entrada, salida):
    e = cargar_escenario(entrada)
    plan = optimizar(e)
    diarios, detalle = tabular(e, plan)
    total_tms = sum(d["alimentacion_tms"] for d in diarios)
    total_cu = sum(d["cu_contenido_t"] for d in diarios)
    total_tmh = sum(d["alimentacion_tmh"] for d in diarios)
    bajo, alto = e.corredor_objetivo
    resumen = {
        "mina": e.mina,
        "estado": plan.estado,
        "brecha_relativa_solver": plan.brecha_relativa,
        "objetivo_equivalente_min": plan.objetivo_equivalente_min,
        "dias": len(diarios),
        "dias_en_corredor_objetivo_nominal": sum(bajo <= d["ley_cu_pct"] <= alto for d in diarios),
        "alimentacion_total_tmh": total_tmh,
        "alimentacion_total_tms": total_tms,
        "ley_campana_cu_pct": 100 * total_cu / total_tms,
        "cu_contenido_total_t": total_cu,
        "viajes_totales": sum(d["viajes"] for d in diarios),
        "ley_diaria_min_cu_pct": min(d["ley_cu_pct"] for d in diarios),
        "ley_diaria_max_cu_pct": max(d["ley_cu_pct"] for d in diarios),
        "extremo_inferior_min_cu_pct": min(d["ley_inferior_cu_pct"] for d in diarios),
        "extremo_superior_max_cu_pct": max(d["ley_superior_cu_pct"] for d in diarios),
        "stock_final_total_tmh": sum(r.stock_tmh for r in e.rumas) - total_tmh,
        "uso_flota_max_pct": max(d["uso_flota_pct"] for d in diarios),
    }

    salida.mkdir(parents=True, exist_ok=True)
    escribir_csv(salida / "plan_diario.csv", diarios)
    escribir_csv(salida / "retiro_por_ruma.csv", detalle)
    graficar(e, plan.viajes, diarios, salida)
    (salida / "resumen.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    return resumen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--escenario", type=Path, default=RAIZ / "datos/mirador_ceniza.json")
    parser.add_argument("--salida", type=Path, default=RAIZ / "resultados")
    args = parser.parse_args()
    try:
        resumen = ejecutar(args.escenario, args.salida)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Error: {error}\n")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

