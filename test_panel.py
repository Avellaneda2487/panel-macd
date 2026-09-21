"""Tests del generador del panel. Sin red: todo sobre series armadas a mano."""

import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import panel

NY = ZoneInfo("America/New_York")
BA = ZoneInfo("America/Argentina/Buenos_Aires")


def serie(valores, inicio="2026-01-01"):
    fechas = pd.bdate_range(inicio, periods=len(valores))
    return pd.Series([float(v) for v in valores], index=fechas)


def tabla(hist, macd=None):
    """Tabla MACD minima. Si no se da el MACD, se usa el histograma."""
    h = serie(hist)
    m = serie(macd) if macd is not None else h
    return pd.DataFrame({"hist": h, "macd": m})


def cruces(hist, macd=None, cierres=None, umbral=None):
    c = serie(cierres if cierres is not None else [100] * len(hist))
    return panel.cruces_de(tabla(hist, macd), c, umbral=umbral, calentamiento=0)


def tipos(lista):
    return [x["tipo"] for x in lista]


# ------------------------------------------------------ cruces sin filtro


def test_cruce_bajista_se_marca_como_salida():
    c = cruces([0.4, 0.1, -0.2])
    assert tipos(c) == ["salida"]
    assert c[0]["fecha"] == "2026-01-05"


def test_sin_cambio_de_signo_no_hay_cruces():
    assert cruces([0.4, 0.5, 0.6]) == []


def test_secuencia_completa_conserva_el_orden():
    assert tipos(cruces([0.5, -1, 0.5, -0.5, 0.2])) == [
        "salida", "entrada", "salida", "entrada",
    ]


def test_cero_exacto_sigue_el_criterio_del_detector():
    # detectar_cruce cuenta el cero del lado bajista: 0.4 -> 0.0 no cruza,
    # 0.0 -> 0.3 si. Panel y detector no pueden discrepar.
    assert tipos(cruces([0.4, -0.1, 0.0, 0.3])) == ["salida", "entrada"]


def test_la_entrada_trae_la_fecha_y_el_cierre_de_su_rueda():
    c = cruces([0.5, -1, 0.5], cierres=[10, 11, 12])
    assert c[-1] == {"fecha": "2026-01-05", "tipo": "entrada", "cierre": 12.0, "fondo": -9.09}


# ------------------------------------------------------ filtro de entrada


def test_entrada_con_fondo_hondo_pasa_el_filtro():
    #        salida        fondo -5 %      entrada
    hist = [0.5, -0.5, -1.0, -0.4, 0.3]
    macd = [1.0, -1.0, -5.0, -4.0, -3.0]
    c = cruces(hist, macd, umbral=-3.0)
    assert tipos(c) == ["salida", "entrada"]
    assert c[-1]["fondo"] == -5.0


def test_entrada_con_fondo_corto_se_ignora():
    hist = [0.5, -0.5, -1.0, -0.4, 0.3]
    macd = [1.0, -1.0, -2.0, -1.5, -1.0]
    assert tipos(cruces(hist, macd, umbral=-3.0)) == ["salida"]


def test_el_umbral_se_mide_en_porcentaje_del_precio():
    # El mismo MACD de -3 dolares es -3 % en un papel de 100 y -2,97 % en uno de 101.
    hist = [0.5, -0.5, -1.0, 0.3]
    macd = [1.0, -1.0, -3.0, -2.0]
    a = cruces(hist, macd, cierres=[100] * 4, umbral=-3.0)
    b = cruces(hist, macd, cierres=[101] * 4, umbral=-3.0)
    assert tipos(a) == ["salida", "entrada"]
    assert tipos(b) == ["salida"]


def test_el_fondo_se_mide_solo_desde_la_ultima_salida():
    # Un pozo hondo antes de una salida anterior no habilita la entrada.
    hist = [0.5, -0.5, 0.5, -0.5, 0.3]
    macd = [1.0, -9.0, -8.0, -1.0, -0.5]
    c = cruces(hist, macd, umbral=-3.0)
    assert tipos(c) == ["salida", "entrada", "salida"]
    assert c[1]["fecha"] == "2026-01-05"


def test_entrada_sin_salida_previa_se_ignora():
    assert cruces([-1, -1, 0.5], macd=[-9, -9, -8], umbral=-3.0) == []


def test_la_salida_no_tiene_filtro():
    # Cruce a la baja con el MACD muy arriba de cero: igual es salida.
    c = cruces([0.5, -0.1], macd=[40.0, 39.0], umbral=-3.0)
    assert tipos(c) == ["salida"]


def test_el_calentamiento_descarta_los_cruces_del_arranque():
    t = tabla([0.5, -0.5, 0.5, -0.5])
    c = serie([100] * 4)
    assert len(panel.cruces_de(t, c, umbral=None, calentamiento=0)) == 3
    assert len(panel.cruces_de(t, c, umbral=None, calentamiento=3)) == 1


# ------------------------------------------------------------ rueda en curso


def ts(fecha):
    return pd.Timestamp(fecha, tz=NY)


def test_rueda_de_hoy_con_el_mercado_abierto_esta_en_curso():
    assert panel.rueda_en_curso(ts("2026-09-21"), datetime(2026, 9, 21, 10, 0, tzinfo=NY))


def test_rueda_de_hoy_despues_del_cierre_esta_cerrada():
    assert not panel.rueda_en_curso(ts("2026-09-21"), datetime(2026, 9, 21, 16, 30, tzinfo=NY))


def test_rueda_de_ayer_esta_cerrada():
    assert not panel.rueda_en_curso(ts("2026-09-18"), datetime(2026, 9, 21, 10, 0, tzinfo=NY))


def test_la_hora_se_lee_en_nueva_york():
    # 16:30 en Buenos Aires son 15:30 en Nueva York: todavia abierto.
    # Leida sin convertir, la hora pasaria el cierre.
    assert panel.rueda_en_curso(ts("2026-09-21"), datetime(2026, 9, 21, 16, 30, tzinfo=BA))


# -------------------------------------------------------------------- lectura


def ondas(n=260):
    return serie([100 + 12 * math.sin(i / 11) for i in range(n)], inicio="2025-01-01")


def test_lectura_arma_las_claves_que_espera_la_plantilla():
    d = panel.lectura_de("XXX", ondas(), balance="2026-10-01")
    assert set(d) == {
        "cierre", "fecha", "estado", "provisoria", "cruce", "entrada", "balance", "serie",
    }
    assert set(d["serie"][0]) == {"f", "c", "h", "m", "s"}


def test_la_serie_se_recorta_a_las_ruedas_pedidas():
    assert len(panel.lectura_de("XXX", ondas(300), None)["serie"]) == panel.RUEDAS_SERIE


def test_hist_es_macd_menos_senal():
    p = panel.lectura_de("XXX", ondas(), None)["serie"][-1]
    assert p["h"] == pytest.approx(p["m"] - p["s"], abs=0.002)


def test_pocas_ruedas_devuelve_none():
    assert panel.lectura_de("XXX", ondas(20), None) is None


def test_papel_sin_entradas_validas_igual_se_lee():
    # Papel plano: nunca cruza. Tiene que seguir en el panel por si esta tildado.
    d = panel.lectura_de("XXX", serie([100.0] * 200), None)
    assert d is not None
    assert d["cruce"] is None and d["entrada"] is None


def test_sin_hora_la_rueda_no_es_provisoria():
    assert panel.lectura_de("XXX", ondas(), None)["provisoria"] is False


def test_con_el_mercado_abierto_la_ultima_rueda_es_provisoria():
    c = ondas()
    ahora = datetime.combine(c.index[-1].date(), datetime.min.time()).replace(hour=10, tzinfo=NY)
    assert panel.lectura_de("XXX", c, None, ahora=ahora)["provisoria"] is True


def test_un_cruce_de_una_rueda_cerrada_no_es_provisorio_aunque_hoy_este_abierto():
    c = ondas()
    ahora = datetime.combine(c.index[-1].date(), datetime.min.time()).replace(hour=10, tzinfo=NY)
    d = panel.lectura_de("XXX", c, None, ahora=ahora)
    assert d["provisoria"] is True
    assert d["cruce"]["fecha"] != d["fecha"], "precondicion: el ultimo cruce es de otra rueda"
    assert d["cruce"]["provisorio"] is False


def test_un_cruce_en_la_rueda_en_curso_se_marca_provisorio():
    c = ondas()
    t = panel.calcular_macd(c)
    todos = panel.cruces_de(t, c)
    ultimo = pd.Timestamp(todos[-1]["fecha"])
    recorte = c.loc[:ultimo]
    ahora = datetime.combine(ultimo.date(), datetime.min.time()).replace(hour=10, tzinfo=NY)
    d = panel.lectura_de("XXX", recorte, None, ahora=ahora)
    assert d["cruce"]["provisorio"] is True
    cerrada = panel.lectura_de("XXX", recorte, None)
    assert cerrada["cruce"]["provisorio"] is False


# --------------------------------------------------------------------- render


def plantilla(tmp_path, texto="<script>const DATOS = __DATOS__;</script>"):
    p = tmp_path / "p.html"
    p.write_text(texto, encoding="utf-8")
    return p


def test_render_reemplaza_el_marcador_por_json_valido(tmp_path):
    html = panel.render({"AAA": {"cierre": 1.0}}, plantilla(tmp_path))
    crudo = html.split("const DATOS = ")[1].split(";</script>")[0]
    assert json.loads(crudo) == {"AAA": {"cierre": 1.0}}


def test_render_falla_si_la_plantilla_no_tiene_marcador(tmp_path):
    with pytest.raises(ValueError):
        panel.render({}, plantilla(tmp_path, "<html></html>"))


def test_render_escapa_el_cierre_de_script(tmp_path):
    html = panel.render({"A": {"x": "</script>"}}, plantilla(tmp_path))
    assert "</script>" not in html.split("const DATOS = ")[1].split(";<")[0]


def test_render_pone_la_marca_de_actualizacion(tmp_path):
    p = plantilla(tmp_path, "<script>const DATOS = __DATOS__;</script><i>__ACTUALIZADO__</i>")
    html = panel.render({}, p, actualizado="21/09/2026 11:04")
    assert "21/09/2026 11:04" in html and "__ACTUALIZADO__" not in html
