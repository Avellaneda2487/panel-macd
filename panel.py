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

import csv
import json
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
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

AQUI = Path(__file__).resolve().parent

# Universo: la nomina de CEDEARs del escaner, solo acciones. Los ETF quedan
# fuera. El archivo es una copia de escaner/datos/universo_cedears.csv.
ARCHIVO_UNIVERSO = AQUI / "universo_cedears.csv"
HILOS = 8                   # descargas en paralelo

RUEDAS_SERIE = 120          # ruedas que viajan al navegador
VELAS_MINIMAS = 60          # por debajo de esto la EMA no se asento

# Entrada clara: entre la ultima Salida y el cruce al alza, el MACD tuvo que
# tocar un fondo de este porcentaje del precio o mas abajo. El MACD se mide
# en dolares; pasarlo a porcentaje hace comparable el umbral entre papeles.
UMBRAL_FONDO = -1.3

# Ruedas iniciales que no se leen: las EMAs arrancan en el mismo valor y el
# primer cambio de signo del histograma es un artefacto del calculo.
CALENTAMIENTO = 100

NY = ZoneInfo("America/New_York")
CIERRE_NY = (16, 0)
PLANTILLA = AQUI / "plantilla.html"
SALIDA = AQUI / "docs" / "index.html"


# --------------------------------------------------------------------- cruces


def cruces_de(
    tabla: pd.DataFrame,
    cierres: pd.Series,
    umbral: float | None = UMBRAL_FONDO,
    calentamiento: int = CALENTAMIENTO,
) -> list[dict]:
    """Cruces validos, en orden.

    Salida: todo cruce a la baja.
    Entrada: cruce al alza cuyo fondo previo (el minimo del MACD desde la
    ultima Salida, en % del cierre de esa rueda) llega al umbral. Un cruce al
    alza que no llega se ignora, y el papel conserva su ultima senal valida.
    Una entrada sin Salida previa en la historia leida tambien se ignora.

    Cada rueda se compara contra la anterior con `detectar_cruce`, el mismo
    criterio del detector de alertas.
    """
    hist, macd = tabla["hist"], tabla["macd"]
    salida: list[dict] = []
    ultima_salida: int | None = None

    for i in range(max(1, calentamiento), len(hist)):
        tipo = detectar_cruce(hist.iloc[i - 1 : i + 1])
        if not tipo:
            continue
        f = hist.index[i]
        cruce = {"fecha": str(f.date()), "tipo": tipo, "cierre": round(float(cierres.loc[f]), 2)}

        if tipo == "salida":
            ultima_salida = i
            salida.append(cruce)
            continue

        if ultima_salida is None:
            continue
        tramo = macd.iloc[ultima_salida : i + 1]
        j = tramo.idxmin()
        fondo = float(tramo.loc[j]) / float(cierres.loc[j]) * 100
        if umbral is None or fondo <= umbral:
            cruce["fondo"] = round(fondo, 2)
            salida.append(cruce)

    return salida


def rueda_en_curso(fecha: pd.Timestamp, ahora: datetime) -> bool:
    """La vela es de hoy y Nueva York todavia no cerro."""
    ahora_ny = ahora.astimezone(NY)
    return fecha.date() == ahora_ny.date() and (ahora_ny.hour, ahora_ny.minute) < CIERRE_NY


# -------------------------------------------------------------------- lectura


def lectura_de(
    ticker: str,
    cierres: pd.Series,
    balance: str | None,
    ahora: datetime | None = None,
) -> dict | None:
    """Arma el registro de un papel. Devuelve None si no alcanza para leerlo.

    Con `ahora`, la ultima vela se marca provisoria si la rueda sigue abierta,
    y tambien el cruce que haya caido en ella.
    """
    cierres = cierres.dropna()
    if len(cierres) < VELAS_MINIMAS:
        print(f"[{ticker}] solo {len(cierres)} ruedas, insuficiente")
        return None

    tabla = calcular_macd(cierres)
    todos = cruces_de(tabla, cierres)
    entradas = [c for c in todos if c["tipo"] == "entrada"]

    ultima = str(cierres.index[-1].date())
    provisoria = bool(ahora) and rueda_en_curso(cierres.index[-1], ahora)

    def marcar(c: dict | None) -> dict | None:
        if c is None:
            return None
        return {**c, "provisorio": provisoria and c["fecha"] == ultima}

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
        "fecha": ultima,
        "estado": "alcista" if float(tabla["hist"].iloc[-1]) > 0 else "bajista",
        "provisoria": provisoria,
        "cruce": marcar(todos[-1] if todos else None),
        "entrada": marcar(entradas[-1] if entradas else None),
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


def cargar_universo(ruta: Path = ARCHIVO_UNIVERSO) -> list[str]:
    """Tickers de tipo accion, en el orden del archivo."""
    with open(ruta, encoding="utf-8", newline="") as f:
        filas = csv.DictReader(f)
        return [
            r["ticker"].strip().upper()
            for r in filas
            if (r.get("tipo") or "").strip().lower() == "accion"
        ]


def _leer_uno(t: str, ahora: datetime) -> tuple[str, dict | None]:
    try:
        velas = descargar(t, periodo=PERIODO_DESCARGA)
    except Exception as e:
        print(f"[{t}] descarga fallida: {type(e).__name__}: {e}")
        return t, None
    if velas.empty or "Close" not in velas:
        print(f"[{t}] sin datos")
        return t, None
    return t, lectura_de(t, velas["Close"], balance_de(t), ahora=ahora)


def construir(universo: list[str] | None = None, ahora: datetime | None = None) -> dict:
    universo = universo if universo is not None else cargar_universo()
    ahora = ahora or datetime.now(NY)
    with ThreadPoolExecutor(max_workers=HILOS) as pool:
        resultados = dict(pool.map(lambda t: _leer_uno(t, ahora), universo))

    # Se conserva el orden del universo: el resultado no depende de que hilo termino antes.
    datos = {t: resultados[t] for t in universo if resultados.get(t)}

    entradas = sorted(t for t, d in datos.items() if d["cruce"] and d["cruce"]["tipo"] == "entrada")
    en_curso = sum(1 for d in datos.values() if d["provisoria"])
    print(f"{len(datos)} de {len(universo)} papeles leidos, {en_curso} con la rueda en curso")
    print(f"ultima senal Entrada ({len(entradas)}): {' '.join(entradas) or '-'}")
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
