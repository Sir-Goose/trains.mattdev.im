import requests

def get_data():
    try:
        with open('key', 'r') as f:
            API_KEY = f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError("The 'key' file was not found. Please create a file named 'key' in the same directory containing only your API key.")

    BASE_URL = 'https://api1.raildata.org.uk/1010-live-arrival-and-departure-boards-arr-and-dep1_1/LDBWS/api/20220120'
    CRS_CODE = 'LHD'

    url = f'{BASE_URL}/GetArrivalDepartureBoard/{CRS_CODE}'

    headers = {
        'x-apikey': API_KEY,
        'User-Agent': 'curl/8.7.1'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        print(data)
    else:
        print(f'Error: {response.status_code} - {response.text}')

class Board():
    departures = []
    arrivals = []

class DepartureTrain:
    scheduled_departure_time = None
    expected_departure_time = None
    platform = None
    status = None


class ArrivalTrain:
    scheduled_arrival_time = None
    expected_arrival_time = None
    platform = None
    status = None