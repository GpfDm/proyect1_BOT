from datetime import time 
from datetime import datetime
import pytz
from src.main.IBClient.ohlc.Data import Ohlc


# CONDITIONS
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
    FUTURE IMPLEMENTATIONS:

    def bar_close_above_hod() -->

    def shares_rotation(self) --> float:

       Session volume so far / number of shares available to trade.
    '''

# STRATEGIES
class LONG10MIN():
    '''
    Opening strategy (9:40 - 9:50 ET).
    Returns 1 if all conditions are met, 0 otherwise.
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

def _place_order(ohlc: Ohlc, tp_pct: float, sl_pct: float):
    '''
    Internal use: PositionManager calls this function after checking
    available slots and liquidity. Do not call it directly from the main loop.
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
    Opening strategy (9:30 - 9:40 ET).
    Returns 1 if all conditions are met, 0 otherwise.

    Strategy conditions:
     Premarket volume: 300k MAX
     Market cap: 200 million MAX
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
    1.12 opportunities per month.
    
    IDEA:
    High-volatility Chinese stocks that break the HOD
    close to the end of the session. Because they have a low float,
    these moves can trigger a strong short squeeze.

    CONDITIONS:
    TIME OF DAY > 14:00
    BAR CLOSE > HOD
    SHARES ROTATION > 3

    SCANNER REQUIREMENTS:
    Market cap max 200 million
    Shares float max 20 million
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
    PREVIOUS DAY FILTERS:
    VOLUME: Min 5 million
    MARKET CAP AT OPEN: Max 200 million
    SHARES FLOAT: 20 million

    CONDITIONS:
    ELAPSED TIME FROM LOD: 2 minutes
    CUMULATIVE SESSION VOLUME: > 400,000
    SHARES ROTATION: < 0.5
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
