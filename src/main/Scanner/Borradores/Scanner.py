import requests as rq
# Library Imports
import requests
import urllib3
import json
import time


# Ignore insecure error messages
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
class Scanner:

    def __init__(self):
        self.tickers = []
        self.status = False
    async def get_scanner_data(self,URL):
      data = None
      try: 
        respuesta =  rq.get(URL,timeout=1)
        respuesta.raise_for_status()
        print("Success: ", respuesta.json())
        data = respuesta.json() #Información de la petición.
        self.status = True
        
      except rq.exceptions.Timeout:
          print("Request time out")
      except rq.exceptions.RequestException as e:
          print("Request failed: ", e)
      except ValueError:
          print("JSONDecodeError")

      return data
    
    def reqIserverScanner(self):
      base_url = "https://localhost:5000/v1/api/"
      endpoint = "iserver/scanner/run"

      scan_body = {
        "instrument": "STK",
        "location": "STK.US.MAJOR",
        "type": "TOP_PERC_GAIN",
        #Filtros para el scanner.
        "filter": [
            {
                "code":"priceAbove",
                "value":101
            },
            {
                "code":"priceBelow",
                "value":110
            }
        ]
    }
      while(self.status):
       try:
        scan_req = requests.post(url=base_url+endpoint, verify=False, json=scan_body)
        scan_json = json.dumps(scan_req.json(), indent=2)

        print(scan_req.status_code)
        print(scan_json)
        # Suponiendo que el archivo json me devuelve en cada recurso el simbolo de la acción.
        for simbolo in scan_json:
          self.tickers.append(simbolo["symbol"]) ##DUDAS en la forma de meter los símbolos
       except requests.exceptions.RequestException:
         print("Error en la request")
       except ValueError as e:
         print("Error: ", e)
       time.sleep(5) # Que espere 5 segundos por cada petición a scanner.
    '''
    scanParams() --> para saber que información quiero tener en cuenta 
    (devuelve un archivo con miles de líneas de scanner)
    '''
    async def scanParams():
     base_url = "https://localhost:5000/v1/api/"
     endpoint = "iserver/scanner/params"

     params_req = requests.get(url=base_url+endpoint, verify=False)
     params_json = json.dumps(params_req.json(), indent=2)

     paramFiles = open("./scannerParams.xml", "w")
    
     for i in params_json:
        paramFiles.write(i)

     paramFiles.close()

     print(params_req.status_code)

    def scanner_disabled(self):
       self.status = False

       
