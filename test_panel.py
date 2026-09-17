"""Tests del generador del panel. Sin red: todo sobre series armadas a mano."""

import json

import pandas as pd
import pytest

import panel


# ------------------------------------------------------------------- cruces


def serie(valores):
    fechas = pd.bdate_range("2026-01-01", periods=len(valores))
    return pd.Series(valores, index=fechas)


def test_cruce_alcista_se_marca_como_entrada():
    c = panel.cruces_de(serie([-1.0, -0.5, 0.3, 0.8]), serie([10, 11, 12, 13]))
    assert [x["tipo"] for x in c] == ["entrada"]
    assert c[0]["fecha"] == "2026-01-05"
    assert c[0]["cierre"] == 12.0


def test_cruce_bajista_se_marca_como_salida():
    c = panel.cruces_de(serie([0.4, 0.1, -0.2]), serie([10, 11, 12]))
    assert [x["tipo"] for x in c] == ["salida"]


def test_sin_cambio_de_signo_no_hay_cruces():
    assert panel.cruces_de(serie([0.4, 0.5, 0.6]), serie([1, 2, 3])) == []


def test_cero_exacto_no_dispara_dos_veces():
    # +, 0, + : el histograma toca cero sin cambiar de lado.
    c = panel.cruces_de(serie([0.4, 0.0, 0.3]), serie([1, 2, 3]))
    assert [x["tipo"] for x in c] == ["entrada"]
    assert c[0]["fecha"] == "2026-01-05"


def test_secuencia_completa_conserva_el_orden():
    c = panel.cruces_de(serie([-1, 0.5, -0.5, 0.2]), serie([1, 2, 3, 4]))
    assert [x["tipo"] for x in c] == ["entrada", "salida", "entrada"]


# -------------------------------------------------------------------- lectura


def cierres_falsos(n=200):
    import math

    return serie([100 + 10 * math.sin(i / 9) for i in range(n)])


def test_lectura_arma_las_claves_que_espera_la_plantilla():
    d = panel.lectura_de("XXX", cierres_falsos(), balance="2026-10-01")
    assert set(d) == {"cierre", "fecha", "estado", "cruce", "entrada", "balance", "serie"}
    assert set(d["serie"][0]) == {"f", "c", "h", "m", "s"}
    assert d["cruce"]["tipo"] in ("entrada", "salida")
    assert d["entrada"]["tipo"] == "entrada"


def test_la_serie_se_recorta_a_las_ruedas_pedidas():
    d = panel.lectura_de("XXX", cierres_falsos(300), balance=None)
    assert len(d["serie"]) == panel.RUEDAS_SERIE


def test_serie_mas_corta_que_el_recorte_no_falla():
    d = panel.lectura_de("XXX", cierres_falsos(80), balance=None)
    assert len(d["serie"]) == 80


def test_hist_es_macd_menos_senal():
    d = panel.lectura_de("XXX", cierres_falsos(), balance=None)
    p = d["serie"][-1]
    assert p["h"] == pytest.approx(p["m"] - p["s"], abs=0.002)


def test_sin_cruces_devuelve_none():
    plana = serie([100.0] * 120)
    assert panel.lectura_de("XXX", plana, balance=None) is None


def test_pocas_ruedas_devuelve_none():
    assert panel.lectura_de("XXX", cierres_falsos(20), balance=None) is None


# --------------------------------------------------------------------- render


def test_render_reemplaza_el_marcador_por_json_valido(tmp_path):
    plantilla = tmp_path / "p.html"
    plantilla.write_text("<script>const DATOS = __DATOS__;</script>", encoding="utf-8")
    html = panel.render({"AAA": {"cierre": 1.0}}, plantilla)
    assert "__DATOS__" not in html
    crudo = html.split("const DATOS = ")[1].split(";</script>")[0]
    assert json.loads(crudo) == {"AAA": {"cierre": 1.0}}


def test_render_falla_si_la_plantilla_no_tiene_marcador(tmp_path):
    plantilla = tmp_path / "p.html"
    plantilla.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(ValueError):
        panel.render({}, plantilla)


def test_render_escapa_el_cierre_de_script(tmp_path):
    plantilla = tmp_path / "p.html"
    plantilla.write_text("<script>const DATOS = __DATOS__;</script>", encoding="utf-8")
    html = panel.render({"A": {"x": "</script>"}}, plantilla)
    assert "</script>" not in html.split("const DATOS = ")[1].split(";<")[0]


def test_render_pone_la_marca_de_actualizacion(tmp_path):
    plantilla = tmp_path / "p.html"
    plantilla.write_text(
        "<script>const DATOS = __DATOS__;</script><i>__ACTUALIZADO__</i>",
        encoding="utf-8",
    )
    html = panel.render({}, plantilla, actualizado="17/09/2026 19:04")
    assert "17/09/2026 19:04" in html
    assert "__ACTUALIZADO__" not in html
