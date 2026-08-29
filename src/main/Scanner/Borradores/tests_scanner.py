from Scanner import Scanner

def test_valid_json():
    scanner = Scanner()
    url = "https://jsonplaceholder.typicode.com/todos/1"
    
    data = scanner.get_scanner_data(url)
    
    assert data is not None
    assert isinstance(data, dict)
    assert "id" in data
  # asumiendo que tu clase está en scanner.py
print("test1")
test_valid_json()
def test_google_url():
    scanner = Scanner()
    url = "https://www.google.com"
    
    data = scanner.get_scanner_data(url)
    
    assert data is None  # porque Google no devuelve JSON
print("test2")

test_google_url()
def test_timeout():
    scanner = Scanner()
    
    # URL que no responde rápido (simulada)
    url = "https://10.255.255.1"
    
    data = scanner.get_scanner_data(url)
    
    assert data is None
print("test3")
test_timeout()


'''
test1
Success:  {'userId': 1, 'id': 1, 'title': 'delectus aut autem', 'completed': False}
test2
Request failed:  Expecting value: line 1 column 1 (char 0)
test3
Request time out
'''