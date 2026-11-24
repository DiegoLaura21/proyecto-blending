# Guía para planificar con tus propias rumas

Usa esta guía si reúnes los datos de geología, cancha y planta y quieres obtener una propuesta diaria de retiros. Cada corrida parte del stock disponible al inicio del periodo, genera un plan en viajes completos de ruma a chancado y deja un saldo por ruma para el siguiente periodo.

## 1. Abre el proyecto y prepara Python

En GitHub, usa **Code → Download ZIP** y descomprime el proyecto. Si ya tienes los archivos, abre esa carpeta. En la terminal, ubícate en la raíz que contiene `requirements.txt`, `datos/` y `src/`. Necesitas Python 3.11 o posterior.

**Windows PowerShell**

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS o Linux**

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

El resto de la guía usa el comando de Windows. En macOS o Linux, reemplaza `.\.venv\Scripts\python.exe` por `.venv/bin/python`.

## 2. Ejecuta la plantilla antes de editarla

La [plantilla de dos rumas](../datos/plantilla_geologo.json) contiene datos ficticios, una fecha y un objetivo de **24.000 TMH**. Sirve para comprobar la instalación y familiarizarte con las salidas.

```powershell
.\.venv\Scripts\python.exe src/planificar.py --escenario datos/plantilla_geologo.json --salida resultados/tutorial
```

Al finalizar, se imprime un resumen con el estado y se generan dos CSV, un JSON y tres PNG en `resultados/tutorial`. La plantilla de referencia produce **100 viajes**, **22.579,2 toneladas secas** y una mezcla de **0,223265 % Cu**. El intervalo calculado es **0,208571–0,237959 % Cu**. El modelo utiliza **2.792 de 2.880 minutos efectivos de flota**.

| Ruma | Viajes | Retiro (TMH) | Saldo (TMH) |
| --- | ---: | ---: | ---: |
| BAJA-01 | 52 | 12.480 | 6.720 |
| ALTA-01 | 48 | 11.520 | 5.280 |
| **Total** | **100** | **24.000** | **12.000** |

Para comprobar la ley, la primera ruma aporta 12.480 × (1 − 4/100) = **11.980,8 TMS** y la segunda aporta 11.520 × (1 − 8/100) = **10.598,4 TMS**. Entre ambas contienen **50,41152 t de Cu**. Dividir ese cobre entre 22.579,2 TMS y multiplicar por 100 da **0,223265 % Cu**.

## 3. Prepara tu archivo de escenario

Guarda una copia de la plantilla como `datos/mi_mina.json`. Si necesitas varias fechas y más rumas, también puedes copiar el [escenario semanal de Mirador de Ceniza](../datos/mirador_ceniza.json). Edita los valores con un editor de texto. Conserva los nombres de los campos, las comillas del texto y los corchetes de las listas. En JSON usa un punto decimal y omite los separadores de miles. Por ejemplo, escribe `60000` para 60.000 TMH y `0.225` para 0,225 % Cu.

### Parámetros generales

| Campo | Qué ingresar |
| --- | --- |
| `mina` | El nombre que aparecerá en el escenario y los gráficos. |
| `ley_min_cu_pct`, `ley_max_cu_pct` | Los límites de ley diaria acordados con planta, expresados en porcentaje. Para 0,15–0,30 % Cu, escribe `0.15` y `0.30`. |
| `ley_objetivo_cu_pct` | El valor preferido dentro de la banda. Usa, por ejemplo, `0.225`. |
| `tolerancia_objetivo_pp` | El margen a cada lado de la meta preferida, en puntos porcentuales. Con `0.225` y un margen de `0.002`, el corredor preferido es 0,223–0,227 % Cu. |
| `payload_tmh` | La carga húmeda efectiva por viaje, común a los camiones del escenario. Usa, por ejemplo, `240` TMH si coincide con tu operación. |
| `penalizacion_min_por_t_cu`, `tiempo_limite_s` | Empieza con `1200` y `30`. El primer valor pondera la cercanía a la meta frente al tiempo de acarreo. El segundo limita el tiempo de cálculo. |

La **banda de planta** es obligatoria. El **corredor preferido** orienta la solución y puede admitir desvíos cuando el plan sigue cumpliendo la banda.

### Una fila por ruma en `rumas`

| Campo | Qué ingresar y de dónde sacarlo |
| --- | --- |
| `id`, `nombre` | Código único y nombre de la ruma tal como aparecen en el control de cancha. |
| `stock_tmh` | Inventario húmedo físicamente disponible al inicio del horizonte. Usa el corte de inventario que corresponda al plan. |
| `cu_pct` | Ley representativa de Cu en base seca. Usa la misma definición de cobre en todas las rumas y en las especificaciones de planta. |
| `humedad_pct` | Porcentaje de agua respecto a la masa húmeda. Escribe `4` para 4 %. |
| `incertidumbre_pp` | Margen de variación de ley que quieras cubrir. Con `cu_pct: 0.12` e `incertidumbre_pp: 0.01`, la ley se evalúa entre 0,11 % y 0,13 % Cu. Ingresa `0` si vas a ejecutar un escenario estrictamente nominal. |
| `retiro_max_tmh_dia` | Cuánto se puede retirar de esa ruma en un día según carguío y acceso. Puedes usar `0` para excluir una ruma durante el horizonte. |
| `ciclo_min` | Minutos por viaje completo de la ruma a chancado, incluyendo carga, ida, descarga y retorno. Usa tiempos representativos del tramo. |

### Una fila por jornada en `dias`

| Campo | Qué ingresar |
| --- | --- |
| `fecha` | Una fecha por jornada en formato `AAAA-MM-DD`, en orden y sin repetir. |
| `planta_tmh` | Alimentación objetivo en toneladas métricas **húmedas**. Si tu meta de planta se expresa en toneladas secas, define primero una meta húmeda consistente con la humedad prevista y verifica `alimentacion_tms` en la salida. |
| `tolerancia_tmh` | Desviación húmeda permitida. Con carga de 240 TMH, 24.000 TMH y tolerancia `0` son compatibles. Para una meta de 24.100 TMH, una tolerancia de 100 TMH permite un plan de 24.000 TMH. |
| `camiones`, `horas_efectivas` | Camiones disponibles para el tramo cancha–chancado y horas efectivas por camión. Introduce un número entero de camiones y descuenta de las horas las paradas que ya hayas considerado en tu disponibilidad. |

## 4. Ejecuta tu escenario

Usa una carpeta de salida propia para poder distinguir versiones y comparar corridas.

```powershell
.\.venv\Scripts\python.exe src/planificar.py --escenario datos/mi_mina.json --salida resultados/mi_mina
```

Para volcar un cambio de inventario o de ley, guarda el JSON y vuelve a ejecutar. La opción `--help` muestra los argumentos del programa.

## 5. Lee los resultados en este orden

| Archivo | Qué revisar |
| --- | --- |
| `resumen.json` | Confirma el estado. `optimizado` indica que el solver terminó dentro de su tolerancia. `factible_con_limite` indica que guardó un plan que pasó las verificaciones, aunque terminó por un límite antes de demostrar la misma calidad de optimización. Revisa también `brecha_relativa_solver` y `ley_campana_cu_pct`. |
| `plan_diario.csv` | Revisa cada fecha. `alimentacion_tmh` se compara con `objetivo_tmh`. `ley_cu_pct` es la ley nominal y `ley_inferior_cu_pct` / `ley_superior_cu_pct` muestran los extremos según los márgenes ingresados. Revisa `uso_flota_pct` y los minutos disponibles antes de proponer el plan a despacho. |
| `retiro_por_ruma.csv` | Filtra por fecha y lee `ruma`, `viajes` y `retiro_tmh`. Las filas con cero viajes se conservan para el balance. `stock_final_tmh` sirve como referencia para contrastar el cierre con el inventario observado. |
| `01_ley_diaria.png` | Presenta la ley nominal, el intervalo de incertidumbre y la banda de planta. |
| `02_retiro_y_flota.png` y `03_inventario.png` | Muestran la contribución de cada ruma al tonelaje, el uso de flota y el saldo al cierre. |

Una ley de campaña dentro de la banda acompaña el resumen. La revisión operativa se hace **por fecha**, usando también los extremos de ley. Los viajes son conteos diarios para preparar el despacho. El programa considera los minutos totales de flota, y la secuencia de retiro y las colas de chancado se validan aparte.

## 6. Ajusta el escenario si cambian las condiciones

| Mensaje o situación | Qué revisar primero |
| --- | --- |
| El rango a planta no admite un número entero de viajes | Revisa el payload y confirma con planta si procede una tolerancia de tonelaje. |
| La capacidad de retiro, stock o flota no cubre el mínimo | Verifica los stocks de partida, el máximo diario de retiro, los ciclos medidos y la flota asignada de esa fecha. |
| No existe un plan factible | Confirma que las leyes y márgenes de incertidumbre estén en la escala correcta y que haya stock suficiente de ley complementaria. Si persiste, evalúa con planta un nuevo tonelaje o con operaciones una nueva disponibilidad. |
| El archivo tiene un error de JSON | Verifica comillas, comas y corchetes. Revisa que hayas escrito números con punto decimal y sin separadores de miles. |
| Llegó material nuevo o cambiaron las leyes durante la semana | Actualiza el stock y las leyes con los datos reconciliados, elimina las jornadas transcurridas del escenario y ejecuta otra corrida para las fechas pendientes. |

Si el script termina con un error, esa corrida carece de un plan válido. Usa una carpeta nueva al probar un cambio y conserva identificadas las salidas anteriores.

