from datetime import time 
from datetime import datetime
import pytz
from src.main.IBClient.ohlc.Data import Ohlc


# ─────────────────────────────────────────────
#  CONDITIONS
# ─────────────────────────────────────────────
class Conditions():
    def __init__(self, ohlc: Ohlc):
        self.ohlc = ohlc

    def time_of_day(self) -> time:
        et = pytz.timezone("US/Eastern")
        return datetime.now(et).time()

    def change_from_open(self) -> float:
        if not self.ohlc.data:
            return 0
        open_price = self.ohlc.data[0]["open"]
        last_price = self.ohlc.data[-1]["close"]
        return ((last_price - open_price) / open_price) * 100

    def session_volume(self) -> float:
        return sum(bar["volume"] for bar in self.ohlc.data)

    def hod(self) -> float:
        return max(bar["high"] for bar in self.ohlc.data)

    def lod(self) -> float:
        return min(bar["low"] for bar in self.ohlc.data)

    def elapsed_from_hod(self) -> float:
        hod_bar = max(self.ohlc.data, key=lambda x: x["high"])
        return (datetime.now() - datetime.strptime(hod_bar["date"], "%Y%m%d %H:%M:%S")).total_seconds()

    def elapsed_from_lod(self) -> float:
        lod_bar = min(self.ohlc.data, key=lambda x: x["low"])
        return (datetime.now() - datetime.strptime(lod_bar["date"], "%Y%m%d %H:%M:%S")).total_seconds()
    
    '''
    FUTURAS IMPLEMENTACIONES :
    def bar_close_above_hod() --> 
    
    def shares_rotation(self) --> float:
    
       Es el vol de la session hasta el momento / numero de acciones disponibles para tradear.

    '''

# ─────────────────────────────────────────────
#  ESTRATEGIAS
# ─────────────────────────────────────────────
class LONG10MIN():
    '''
    Estrategia de apertura (9:40 - 9:50 ET).
    Devuelve 1 si se cumplen todas las condiciones, 0 si no.
    '''
    def __init__(self, ohlc: Ohlc):
        self.conditions = Conditions(ohlc)

    def check(self) -> int:
        c = self.conditions
        if (c.time_of_day() > time(9, 40)
                and c.time_of_day() < time(9, 50)
                and c.change_from_open() > 0
                and 100_000 < c.session_volume() < 500_000):
            return 1
        return 0

#  FUNCIÓN INTERNA  (usada por PositionManager)
def _place_order(ohlc: Ohlc, tp_pct: float, sl_pct: float):
    '''
    Uso interno: PositionManager llama a esta función tras validar
    slots y liquidez. No llamar directamente desde el loop principal.
    '''
    order = ohlc.buy_order()
    order_id = ohlc.connection.next_id()
    ohlc.entry_order_id = order_id
    ohlc.connection.placeOrder(order_id, ohlc.data_historic.contract, order)
    ohlc.connection.register_order(order_id, ohlc)

    entry_price = ohlc.data[-1]["close"]
    tp_price    = entry_price * (1 + tp_pct)
    sl_price    = entry_price * (1 - sl_pct)
    ohlc.open_position(entry_price, tp_price, sl_price)

class LONG10MIN2():
    '''
    Estrategia de apertura (9:30 - 9:40 ET).
    Devuelve 1 si se cumplen todas las condiciones, 0 si no.

    Para esta estrategia las condiciones son:
     Premarket volume: 300k MAX
     Market cap: 200 Millones MAX
     Open price: 1 MIN
    '''
    def __init__(self, ohlc: Ohlc):
        self.conditions = Conditions(ohlc)

    def check(self) -> int:
        c = self.conditions
        if (c.time_of_day() > time(9, 30)
                and c.time_of_day() < time(9, 40)
                and c.change_from_open() > 2
                and 100_000 < c.session_volume() < 500_000):
            return 1
        return 0
    
class CHINASLOCAS():
    '''
    1.12 oportunidades al mes.
    IDEA:
    Acciones chinas con volatilidad alta
    que rompen el HOD en horas cercanas al close y que al ser low float producen un short 
    Squeeze bastante fuerte.

    CONDITIONS:
    TIME OF THE DAY > 14:00
    BAR CLOSE > HOD
    SHARES ROTATION > 3

    REQUISITOS DE SCANNER:
    Market cap max 200 Millones
    Shares float max 20 Millones
    Gap value min 20%
    '''
    def __init__(self,ohlc: Ohlc):
        self.conditions = Conditions(ohlc)

    def check(self) -> int:
        c = self.conditions
        if (c.time_of_day() > time(14, 00)
                and c.time_of_day() < time(16, 00)
                and c.change_from_open() > 0
                and 100_000 < c.session_volume() < 500_000):
            return 1
        return 0
class PMLONG():
    '''
    PREV DAY FILTERS:
    VOLUMEN: Min 5Millones
    MARKET CAP OPEN: Max 200Millones
    SHARES FLOAT: 20Millones

    CONDITIONS:
    ELAPSED TIME FROM LOD: 2Minutes
    CUMULATIVE SESSION VOLUME: > 400 000
    Shares rotation: < 0.5
    '''
    def __init__(self,ohlc: Ohlc):
        self.conditions = Conditions(ohlc)

    def check(self) -> int:
        c = self.conditions
        if (c.time_of_day() > time(4,00)
                and c.time_of_day() < time(9, 30)
                and c.change_from_open() > 0
                and 100_000 < c.session_volume() < 500_000):
            return 1
        return 0

# ─────────────────────────────────────────────
#  PROBLEMAS RESUELTOS / PENDIENTES
# ─────────────────────────────────────────────
'''
RESUELTOS:
 ✅ Monitoreo activo TP/SL via tickPrice LAST
 ✅ SL duro GTC en broker si el bot se cae
 ✅ Comprobación de liquidez antes de entrar
 ✅ Detección de HALT (tickString tickType=49)
 ✅ Logging persistente de cada trade (trades_log.csv)
 ✅ Filtro de ticks inválidos (price <= 0)
 ✅ Manejo de errores IB (200, 354, 1100-1102, etc.)
 ✅ execDetails: recalibra TP/SL con fill real
 ✅ orderStatus: detecta stop duro ejecutado sin el bot
 ✅ reqPositions al arrancar: recupera posición si bot se reinició
 ✅ Multiposición: máx 5 slots, riesgo fijo por trade
 ✅ Notificación cuando señal no se puede ejecutar (slots llenos / ilíquido)

PENDIENTES (después del paper trading del jueves):
 ⬜ TP/SL dinámico basado en ATR
 ⬜ Tests unitarios de Conditions/LONG10MIN con datos falsos
 ⬜ Backtest de la estrategia sobre datos históricos
'''
