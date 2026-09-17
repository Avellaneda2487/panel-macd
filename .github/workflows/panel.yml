"""Genera el panel HTML de Cruces MACD.

Baja los cierres del universo, calcula el MACD, arma las lecturas y las
inyecta en la plantilla. El resultado es un archivo HTML autocontenido,
listo para publicar.

La capa global (las lecturas) se regenera cada rueda. La capa privada
(qué papeles tiene Laura y desde cuándo) vive en el navegador y no pasa
nunca por acá.

    python panel.py                 -> docs/index.html
    python panel.py salida.html     -> salida.html
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from macd_alertas import (
    PERIODO_DESCARGA,
    calcular_macd,
    descargar,
    detectar_cruce,
)

# ------------------------------------------------------------------ parametros

# Top CEDEARs, solo acciones. Los ETF quedan fuera: no tienen balance.
UNIVERSO = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "MELI", "KO", "JPM", "XOM",
]

RUEDAS_SERIE = 120          # ruedas que viajan al navegador
VELAS_MINIMAS = 60          # por debajo de esto la EMA no se asento
AQUI = Path(__file__).resolve().parent
PLANTILLA = AQUI / "plantilla.html"
SALIDA = AQUI / "docs" / "index.html"


# --------------------------------------------------------------------- cruces


def cruces_de(hist: pd.Series, cierres: pd.Series) -> list[dict]:
    """Todos los cruces del histograma, en orden.

    Usa el mismo criterio que el detector de alertas: compara cada rueda
    contra la anterior con `detectar_cruce`, de modo que el panel y el
    detector nunca puedan discrepar.
    """
    salida: list[dict] = []
    for i in range(1, len(hist)):
        tipo = detectar_cruce(hist.iloc[i - 1 : i + 1])
        if tipo:
            f = hist.index[i]
            salida.append({
                "fecha": str(f.date()),
                "tipo": tipo,
                "cierre": round(float(cierres.loc[f]), 2),
            })
    return salida


# -------------------------------------------------------------------- lectura


def lectura_de(ticker: str, cierres: pd.Series, balance: str | None) -> dict | None:
    """Arma el registro de un papel. Devuelve None si no alcanza para leerlo."""
    cierres = cierres.dropna()
    if len(cierres) < VELAS_MINIMAS:
        print(f"[{ticker}] solo {len(cierres)} ruedas, insuficiente")
        return None

    tabla = calcular_macd(cierres)
    todos = cruces_de(tabla["hist"], cierres)
    entradas = [c for c in todos if c["tipo"] == "entrada"]
    if not todos or not entradas:
        print(f"[{ticker}] sin cruces en la historia cargada")
        return None

    corte = slice(-RUEDAS_SERIE, None)
    serie = [
        {
            "f": str(f.date()),
            "c": round(float(c), 2),
            "h": round(float(h), 3),
            "m": round(float(m), 3),
            "s": round(float(s), 3),
        }
        for f, c, h, m, s in zip(
            cierres.index[corte],
            cierres.iloc[corte],
            tabla["hist"].iloc[corte],
            tabla["macd"].iloc[corte],
            tabla["senal"].iloc[corte],
        )
    ]

    return {
        "cierre": round(float(cierres.iloc[-1]), 2),
        "fecha": str(cierres.index[-1].date()),
        "estado": "alcista" if float(tabla["hist"].iloc[-1]) > 0 else "bajista",
        "cruce": todos[-1],
        "entrada": entradas[-1],
        "balance": balance,
        "serie": serie,
    }


# ------------------------------------------------------------------- descargas


def balance_de(ticker: str) -> str | None:
    """Proxima fecha de balance, si Yahoo la tiene."""
    import yfinance as yf

    try:
        cal = yf.Ticker(ticker).calendar or {}
        fechas = cal.get("Earnings Date") or []
        return str(fechas[0]) if fechas else None
    except Exception as e:
        print(f"[{ticker}] balance no disponible: {type(e).__name__}")
        return None


def construir(universo: list[str] = UNIVERSO) -> dict:
    datos: dict[str, dict] = {}
    for t in universo:
        try:
            velas = descargar(t, periodo=PERIODO_DESCARGA)
        except Exception as e:
            print(f"[{t}] descarga fallida: {type(e).__name__}: {e}")
            continue
        if velas.empty or "Close" not in velas:
            print(f"[{t}] sin datos")
            continue
        lec = lectura_de(t, velas["Close"], balance_de(t))
        if lec:
            datos[t] = lec
            print(f"{t:6} {lec['fecha']}  {lec['estado']:8} "
                  f"{lec['cruce']['tipo']} el {lec['cruce']['fecha']}")
    return datos


# --------------------------------------------------------------------- render


def render(datos: dict, plantilla: Path = PLANTILLA, actualizado: str = "") -> str:
    texto = Path(plantilla).read_text(encoding="utf-8")
    if "__DATOS__" not in texto:
        raise ValueError(f"la plantilla {plantilla} no tiene el marcador __DATOS__")
    crudo = json.dumps(datos, separators=(",", ":"), ensure_ascii=False)
    crudo = crudo.replace("</", "<\\/")  # nada cierra el <script> desde adentro
    return texto.replace("__DATOS__", crudo).replace("__ACTUALIZADO__", actualizado)


# ----------------------------------------------------------------------- main


def main() -> int:
    warnings.filterwarnings("ignore")
    datos = construir()
    if not datos:
        print("ninguna lectura valida, el panel no se reescribe")
        return 1

    ahora = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    html = render(datos, actualizado=ahora.strftime("%d/%m/%Y %H:%M"))

    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SALIDA
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    print(f"{len(datos)} papeles -> {destino} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
