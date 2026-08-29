import threading
import socket
from enum import Enum
from das_trader import DASTraderClient, OrderSide, OrderType, MarketDataManager, SmartLocateManager
from das_trader.strategies import TradingStrategies
from das_trader.market_scanner import MarketScanner
from main.Scanner.Borradores.Scanner import Scanner
  

class ScannerClient():
 def __init__(self):
     self.PORT = 7496 #Te lo tiene que dar DAS
     self.SERVER = "localhost" #la del pc sobremesa (donde esta tws) --> probar hostname.
     self.ADDR = (self.SERVER, self.PORT)
     self.socket = None
     self.scanners : list[Scanner]
 def init_socket(self):
     self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #AF_INET PARA IPV4 Y SOCK STREAM ESTANDAR 
     #self.socket.bind(self.ADDR) #Asignamos a este socket esta dirección.
 def handdle_client(self):
      for scanner in self.scanners:
         if scanner.status == True:
            scanner.reqIserverScanner()
            tickers = scanner.tickers
        #Habría que crear una lista que tenga todos los tickers de cada scanner

 def start(self):
       try:
        self.socket.connect(self.ADDR)
        print(f"[CONNECTION]{self.ADDR} with Scanner")
        print("Conexion", self.socket.getpeername())
        #thread = threading.Thread(target= self.handdle_client) 
        #thread.start()
       except ConnectionRefusedError:
         print("Error: puerto cerrado o conexión no permitida")
       except TimeoutError:
        print("Error: Timeout")
      

 def close(self):
    self.socket.close()
    print("Socket cerrado")

      
def main():
   ibrk = ScannerClient()
   ibrk.init_socket()
   ibrk.start()
   ibrk.close()

if __name__ == "__main__":
    main()

'''
self.socket.listen()
while True:
conn, addr = self.socket.accept() #Se queda esperando en esta línea a recibir una conexión.
#Cuando cree la conexión creo un thread para manegar a dicho usuario
thread = threading.Thread(target= self.handdle_client, args=(conn, addr)) 
thread.start()
print(f"[ACTIVE CONNECTIONS] {threading.active_count()-1} ") #quitamos 1 por el thread que hace star"t
'''

'''
prueba de conexion:
[CONNECTION]('192.168.1.39', 7496) with Scanner
Conexion ('192.168.1.39', 7496)
'''
# PASO 2: CONECTARNOS CON EL SCANNER EN CONCRETO Y RECIBIR INFORMACIÓN