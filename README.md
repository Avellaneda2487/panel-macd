# Panel MACD

Página de Cruces MACD: se regenera sola cada rueda y se publica en GitHub Pages.

## Archivos

| Archivo | Dónde va | Qué hace |
|---|---|---|
| `panel.py` | raíz del repo | baja los cierres, calcula el MACD, arma las lecturas |
| `plantilla.html` | raíz del repo | la página, con el marcador donde entran los datos |
| `test_panel.py` | raíz del repo | 32 tests del generador |
| `universo_cedears.csv` | raíz del repo | copia de la nómina del escáner; el panel toma solo las acciones |
| `panel.yml` | `.github/workflows/panel.yml` | la corrida diaria y la marca de actividad mensual |

Necesita `macd_alertas.py` en el mismo repo: de ahí salen `calcular_macd`, `descargar` y `detectar_cruce`.

## Puesta en marcha desde el navegador, sin git ni Python

1. **Repo.** github.com → New repository → nombre `panel-macd` → **Public** (Pages pide plan pago en repos privados) → Create.
2. **Los archivos de la raíz.** En el repo, botón **Add file** (arriba a la derecha de la lista de archivos) → **Upload files** → arrastrá `panel.py`, `plantilla.html`, `test_panel.py` y `macd_alertas.py` → Commit changes.
   En un repo recién creado y vacío no hay lista de archivos ni botón Add file: la pantalla de bienvenida trae la frase "Get started by creating a new file or uploading an existing file", y ahí **uploading an existing file** es el link.
   Atajo directo en los dos casos: `github.com/<usuario>/<repo>/upload/main`.
3. **El workflow.** Add file → Create new file. En el nombre escribí `.github/workflows/panel.yml`; las barras crean las carpetas solas. Pegá adentro el contenido de `panel.yml` → Commit changes.
4. **Pages.** Settings → Pages → Source: **GitHub Actions**. Una sola vez.
5. **Primera corrida.** Actions → "Panel MACD" → Run workflow → Run workflow. Dos minutos.
6. **El link.** Cuando termina en verde, la URL aparece en el job `publicar`:
   `https://<usuario>.github.io/panel-macd/`. No cambia nunca más.

De ahí en más corre solo todos los días a las 14:07 UTC (11:07 en Buenos Aires). Si Nueva York ya abrió, la rueda del día entra en curso y sus cruces se marcan Provisorio hasta el cierre.

Una vez por mes el workflow deja un commit en `.github/actividad.txt`. GitHub apaga los horarios de un repo público después de 60 días sin actividad, y ese commit lo evita.

## Uso local

```bash
pip install pandas yfinance pytest
python -m pytest -q      # 32 passed
python panel.py          # escribe docs/index.html
```

## Qué sale en pantalla

- **Alerta de Salida** — papeles tildados cuyo último cruce fue bajista. Queda hasta que destildes.
- **Alerta de Entrada** — papeles sin tildar con una Entrada válida dentro de las últimas 3 Ruedas. Entrada válida: cruce al alza después de que el MACD tocó, desde la última Salida, un fondo de −1,3 % del precio o más abajo (`UMBRAL_FONDO` en `panel.py`). Un cruce al alza que no llega se ignora.
- **Tengo** — el resto de lo tildado.

Un papel bajista sin tildar queda fuera de pantalla.

El tilde, el día de entrada, el porcentaje y la fecha del balance viven en el navegador (`localStorage`). Nada de eso sube al repo. Exportar e Importar mueven ese estado entre dispositivos.

## Universo

El universo sale de `universo_cedears.csv`, copia de `escaner/datos/universo_cedears.csv`: todas las filas de tipo `accion`, sin los ETF. Cuando el escáner suma o renombra un CEDEAR, hay que copiar el archivo de nuevo acá.
