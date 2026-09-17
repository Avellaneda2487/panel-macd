"""Detector de cruces MACD sobre la linea de Senal.

Una sola senal: el histograma cambia de signo. El cruce vale este el MACD
por encima o por debajo de cero.

    hist > 0 viniendo de <= 0   ->  ENTRADA
    hist < 0 viniendo de >= 0   ->  SALIDA

Dos informes independientes, cada uno con su propio universo:

    ENTRADA  sobre los papeles vigilados   -> cruces alcistas
    SALIDA   sobre los papeles en cartera  -> cruces bajistas

Cada informe se envia solo si ese dia hubo al menos un cruce de ese tipo.
Los dias sin cruces no generan mail.

Corre una vez por dia despues del cierre de Nueva York. No comparte codigo,
datos ni destinatarios con el escaner de CEDEARs.
"""

from __future__ import annotations

import os
import smtplib
import sys
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

import pandas as pd

# ------------------------------------------------------------------ parametros

# Candidatos a compra: generan alertas de ENTRADA.
TICKERS_VIGILADOS = ["SPY", "AAPL", "NVDA"]

# Papeles ya comprados: generan alertas de SALIDA.
# Provisorio hasta que exista el registro de compras. Cuando ese registro
# exista, esta constante se reemplaza por su lectura y no cambia nada mas.
TICKERS_EN_CARTERA = ["SPY", "AAPL", "NVDA"]

RAPIDA = 12
LENTA = 26
SENAL = 9

# Historia solo como combustible de calculo: las EMAs son recursivas y
# necesitan asentarse. Nada de esto se informa.
PERIODO_DESCARGA = "2y"
VELAS_MINIMAS = 60

NOMBRE_REMITENTE = "Alertas MACD"


# ------------------------------------------------------------------- estructura


@dataclass
class Lectura:
    ticker: str
    fecha: str
    cierre: float
    macd: float
    senal: float
    hist: float
    hist_previo: float
    cruce: str | None
    estado: str


# --------------------------------------------------------------------- calculo


def calcular_macd(
    cierres: pd.Series,
    rapida: int = RAPIDA,
    lenta: int = LENTA,
    senal: int = SENAL,
) -> pd.DataFrame:
    """MACD estandar. hist = macd - senal, por definicion."""
    ema_rapida = cierres.ewm(span=rapida, adjust=False).mean()
    ema_lenta = cierres.ewm(span=lenta, adjust=False).mean()
    linea = ema_rapida - ema_lenta
    linea_senal = linea.ewm(span=senal, adjust=False).mean()
    return pd.DataFrame(
        {"macd": linea, "senal": linea_senal, "hist": linea - linea_senal}
    )


def detectar_cruce(hist: pd.Series) -> str | None:
    """Compara la ultima rueda cerrada contra la anterior."""
    if len(hist) < 2:
        raise ValueError("se necesitan al menos dos ruedas para detectar un cruce")

    hoy = float(hist.iloc[-1])
    ayer = float(hist.iloc[-2])

    if hoy > 0 >= ayer:
        return "entrada"
    if hoy < 0 <= ayer:
        return "salida"
    return None


def estado_actual(hist: pd.Series) -> str:
    return "alcista" if float(hist.iloc[-1]) > 0 else "bajista"


# ------------------------------------------------------------------- descarga


def descargar(ticker: str, periodo: str = PERIODO_DESCARGA) -> pd.DataFrame:
    import yfinance as yf

    return yf.Ticker(ticker).history(period=periodo, interval="1d", auto_adjust=True)


def leer_ticker(ticker: str) -> Lectura | None:
    velas = descargar(ticker)

    if velas.empty or "Close" not in velas:
        print(f"[{ticker}] sin datos")
        return None

    cierres = velas["Close"].dropna()
    if len(cierres) < VELAS_MINIMAS:
        print(f"[{ticker}] solo {len(cierres)} ruedas, insuficiente")
        return None

    tabla = calcular_macd(cierres)

    return Lectura(
        ticker=ticker,
        fecha=str(cierres.index[-1].date()),
        cierre=float(cierres.iloc[-1]),
        macd=float(tabla["macd"].iloc[-1]),
        senal=float(tabla["senal"].iloc[-1]),
        hist=float(tabla["hist"].iloc[-1]),
        hist_previo=float(tabla["hist"].iloc[-2]),
        cruce=detectar_cruce(tabla["hist"]),
        estado=estado_actual(tabla["hist"]),
    )


# --------------------------------------------------------------------- filtros


def entradas(lecturas: list[Lectura]) -> list[Lectura]:
    return [l for l in lecturas if l.cruce == "entrada"]


def salidas(lecturas: list[Lectura]) -> list[Lectura]:
    return [l for l in lecturas if l.cruce == "salida"]


# ---------------------------------------------------------------------- salida


PALETA = {
    "entrada": {"titulo": "Entrada", "color": "#137333", "fondo": "#e8f5e9"},
    "salida": {"titulo": "Salida", "color": "#c5221f", "fondo": "#fce8e6"},
}


def _fila_html(lec: Lectura, tipo: str) -> str:
    p = PALETA[tipo]
    return f"""<tr style="background:{p['fondo']}">
  <td style="padding:8px 12px"><b>{lec.ticker}</b></td>
  <td style="padding:8px 12px;text-align:right">{lec.cierre:,.2f}</td>
  <td style="padding:8px 12px;text-align:right">{lec.macd:+.3f}</td>
  <td style="padding:8px 12px;text-align:right">{lec.senal:+.3f}</td>
  <td style="padding:8px 12px;text-align:right">{lec.hist_previo:+.3f} &rarr; {lec.hist:+.3f}</td>
</tr>"""


def armar_html(lecturas: list[Lectura], tipo: str) -> str:
    p = PALETA[tipo]
    fecha = lecturas[0].fecha if lecturas else str(datetime.now().date())
    filas = "\n".join(_fila_html(l, tipo) for l in lecturas)

    return f"""<html><body style="font-family:Helvetica,Arial,sans-serif;color:#202124">
<h2 style="margin-bottom:2px;color:{p['color']}">{p['titulo']}</h2>
<p style="margin-top:0;color:#5f6368;font-size:13px">
  Rueda del {fecha} &middot; MACD {RAPIDA}/{LENTA}/{SENAL} &middot; diario
</p>
<table cellspacing="0" style="border-collapse:collapse;font-size:14px;border:1px solid #dadce0">
<tr style="background:#f1f3f4;text-align:left">
  <th style="padding:8px 12px">Ticker</th>
  <th style="padding:8px 12px;text-align:right">Cierre</th>
  <th style="padding:8px 12px;text-align:right">MACD</th>
  <th style="padding:8px 12px;text-align:right">Se&ntilde;al</th>
  <th style="padding:8px 12px;text-align:right">Histograma</th>
</tr>
{filas}
</table>
<p style="color:#5f6368;font-size:12px;margin-top:18px">
  El cruce se informa este el MACD por encima o por debajo de cero.
</p>
</body></html>"""


def armar_asunto(lecturas: list[Lectura], tipo: str) -> str:
    return f"MACD {tipo} - " + ", ".join(l.ticker for l in lecturas)


def consola(etiqueta: str, lecturas: list[Lectura]) -> None:
    if not lecturas:
        print(f"{etiqueta}: ninguno hoy")
        return
    for l in lecturas:
        print(
            f"{etiqueta:8} {l.ticker:6} {l.fecha}  cierre {l.cierre:10,.2f}  "
            f"hist {l.hist_previo:+.3f} -> {l.hist:+.3f}"
        )


# ------------------------------------------------------------------------ mail


def enviar(asunto: str, html: str) -> None:
    origen = os.environ.get("MACD_MAIL_ORIGEN")
    clave = os.environ.get("MACD_MAIL_PASS")
    destino = os.environ.get("MACD_MAIL_DESTINO")

    if not (origen and clave and destino):
        print("faltan variables de entorno de mail, no se envia")
        return

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((NOMBRE_REMITENTE, origen))
    msg["To"] = destino
    msg.set_content("Este mail requiere un cliente con HTML.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(origen, clave)
        smtp.send_message(msg)

    print(f"mail enviado a {destino}")


# ------------------------------------------------------------------------ main


def main() -> int:
    cache: dict[str, Lectura | None] = {}

    def leer(ticker: str) -> Lectura | None:
        if ticker not in cache:
            cache[ticker] = leer_ticker(ticker)
        return cache[ticker]

    vigilados = [lec for t in TICKERS_VIGILADOS if (lec := leer(t))]
    cartera = [lec for t in TICKERS_EN_CARTERA if (lec := leer(t))]

    if not vigilados and not cartera:
        print("ninguna lectura valida")
        return 1

    de_entrada = entradas(vigilados)
    de_salida = salidas(cartera)

    consola("entrada", de_entrada)
    consola("salida", de_salida)

    if de_entrada:
        enviar(armar_asunto(de_entrada, "entrada"), armar_html(de_entrada, "entrada"))

    if de_salida:
        enviar(armar_asunto(de_salida, "salida"), armar_html(de_salida, "salida"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
