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
        return data
    else:
        print(f'Error: {response.status_code} - {response.text}')

def fill_board():
    data = get_data()
    
    # Error handling: check if data exists and has trainServices
    if not data or 'trainServices' not in data:
        return None
    
    new_board = Board()
    
    for train in data['trainServices']:
        print(train)
        departure_train = DepartureTrain()
        
        # Basic departure information
        departure_train.scheduled_departure_time = train.get('std')
        departure_train.expected_departure_time = train.get('etd')
        departure_train.platform = train.get('platform', 'TBC')
        departure_train.status = train.get('etd')
        
        # Origin and destination information
        if train.get('origin') and len(train['origin']) > 0:
            departure_train.origin = train['origin'][0].get('locationName')
        
        if train.get('destination') and len(train['destination']) > 0:
            departure_train.destination = train['destination'][0].get('locationName')
        
        # Operator and cancellation information
        departure_train.operator = train.get('operator')
        departure_train.is_cancelled = train.get('isCancelled', False)
        
        # Add train to board's departures list
        new_board.departures.append(departure_train)
    
    return new_board


class Board():
    departures = []
    arrivals = []

class DepartureTrain:
    scheduled_departure_time = None
    expected_departure_time = None
    platform = None
    status = None
    origin = None
    destination = None
    operator = None
    is_cancelled = None


class ArrivalTrain:
    scheduled_arrival_time = None
    expected_arrival_time = None
    platform = None
    status = None

if __name__ == '__main__':
    #get_data()
    fill_board()