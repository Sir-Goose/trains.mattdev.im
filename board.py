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
    
    # Set board metadata
    new_board.location_name = data.get('locationName')
    new_board.crs = data.get('crs')
    new_board.generated_at = data.get('generatedAt')
    new_board.filter_type = data.get('filterType')
    new_board.platform_available = data.get('platformAvailable')
    new_board.are_services_available = data.get('areServicesAvailable')
    
    # Create Train objects for each train service
    for train_data in data['trainServices']:
        print(train_data)
        
        train = Train(
            scheduled_arrival_time=train_data.get('sta'),
            estimated_arrival_time=train_data.get('eta'),
            scheduled_departure_time=train_data.get('std'),
            estimated_departure_time=train_data.get('etd'),
            origin=train_data.get('origin', []),
            destination=train_data.get('destination', []),
            platform=train_data.get('platform', 'TBC'),
            operator=train_data.get('operator'),
            operator_code=train_data.get('operatorCode'),
            service_id=train_data.get('serviceID'),
            service_type=train_data.get('serviceType'),
            length=train_data.get('length', 0),
            is_cancelled=train_data.get('isCancelled', False),
            is_circular_route=train_data.get('isCircularRoute', False),
            is_reverse_formation=train_data.get('isReverseFormation', False),
            filter_location_cancelled=train_data.get('filterLocationCancelled', False),
            future_cancellation=train_data.get('futureCancellation', False),
            future_delay=train_data.get('futureDelay', False),
            detach_front=train_data.get('detachFront', False),
            delay_reason=train_data.get('delayReason')
        )
        
        # Add train to board's trains list
        new_board.trains.append(train)
    
    return new_board


class Board:
    def __init__(self):
        self.trains = []
        self.location_name = None
        self.crs = None
        self.generated_at = None
        self.filter_type = None
        self.platform_available = None
        self.are_services_available = None
    
    @property
    def departures(self):
        """Returns only trains that are departing (have std)"""
        return [train for train in self.trains if train.is_departing]
    
    @property
    def arrivals(self):
        """Returns only trains that are arriving (have sta)"""
        return [train for train in self.trains if train.is_arriving]
    
    @property
    def passing_through(self):
        """Returns trains that are both arriving and departing"""
        return [train for train in self.trains if train.is_passing_through]


class Train:
    def __init__(self, scheduled_arrival_time=None, estimated_arrival_time=None,
                 scheduled_departure_time=None, estimated_departure_time=None,
                 origin=None, destination=None, platform=None, operator=None,
                 operator_code=None, service_id=None, service_type=None,
                 length=0, is_cancelled=False, is_circular_route=False,
                 is_reverse_formation=False, filter_location_cancelled=False,
                 future_cancellation=False, future_delay=False, detach_front=False,
                 delay_reason=None):
        self.scheduled_arrival_time = scheduled_arrival_time
        self.estimated_arrival_time = estimated_arrival_time
        self.scheduled_departure_time = scheduled_departure_time
        self.estimated_departure_time = estimated_departure_time
        self.origin = origin if origin is not None else []
        self.destination = destination if destination is not None else []
        self.platform = platform
        self.operator = operator
        self.operator_code = operator_code
        self.service_id = service_id
        self.service_type = service_type
        self.length = length
        self.is_cancelled = is_cancelled
        self.is_circular_route = is_circular_route
        self.is_reverse_formation = is_reverse_formation
        self.filter_location_cancelled = filter_location_cancelled
        self.future_cancellation = future_cancellation
        self.future_delay = future_delay
        self.detach_front = detach_front
        self.delay_reason = delay_reason
    
    @property
    def is_departing(self):
        """Returns True if train has a scheduled departure time"""
        return self.scheduled_departure_time is not None
    
    @property
    def is_arriving(self):
        """Returns True if train has a scheduled arrival time"""
        return self.scheduled_arrival_time is not None
    
    @property
    def is_passing_through(self):
        """Returns True if train is both arriving and departing"""
        return self.is_arriving and self.is_departing
    
    @property
    def origin_name(self):
        """Helper to get first origin's location name"""
        return self.origin[0]['locationName'] if self.origin else None
    
    @property
    def destination_name(self):
        """Helper to get first destination's location name"""
        return self.destination[0]['locationName'] if self.destination else None
    
    @property
    def destination_via(self):
        """Helper to get 'via' routing info if present"""
        return self.destination[0].get('via') if self.destination else None
    
    @property
    def display_status(self):
        """Smart status string for display"""
        if self.is_cancelled:
            return "Cancelled"
        
        # For departures, prioritize etd
        if self.is_departing:
            if self.estimated_departure_time == "On time":
                return "On time"
            elif self.estimated_departure_time and self.estimated_departure_time != self.scheduled_departure_time:
                return f"Exp {self.estimated_departure_time}"
            return self.estimated_departure_time or "No information"
        
        # For arrivals, use eta
        if self.is_arriving:
            if self.estimated_arrival_time == "On time":
                return "On time"
            elif self.estimated_arrival_time and self.estimated_arrival_time != self.scheduled_arrival_time:
                return f"Exp {self.estimated_arrival_time}"
            return self.estimated_arrival_time or "No information"
        
        return "Unknown"

if __name__ == '__main__':
    board = fill_board()
    
    if board:
        print(f"\n{'='*60}")
        print(f"Board for {board.location_name} ({board.crs})")
        print(f"Generated at: {board.generated_at}")
        print(f"{'='*60}\n")
        
        print(f"Total trains: {len(board.trains)}")
        print(f"Departures: {len(board.departures)}")
        print(f"Arrivals: {len(board.arrivals)}")
        print(f"Passing through: {len(board.passing_through)}")
        
        print(f"\n{'='*60}")
        print("DEPARTURES:")
        print(f"{'='*60}")
        for train in board.departures[:3]:  # Show first 3
            print(f"{train.scheduled_departure_time} to {train.destination_name}")
            print(f"  Platform: {train.platform} | Status: {train.display_status}")
            print(f"  Operator: {train.operator}")
            if train.destination_via:
                print(f"  Via: {train.destination_via}")
            if train.is_passing_through:
                print(f"  ⚡ Passing through (arrives {train.scheduled_arrival_time})")
            print()
        
        if board.passing_through:
            print(f"\n{'='*60}")
            print("PASSING THROUGH:")
            print(f"{'='*60}")
            for train in board.passing_through[:3]:  # Show first 3
                print(f"{train.scheduled_arrival_time} → {train.scheduled_departure_time}")
                print(f"  {train.origin_name} to {train.destination_name}")
                print(f"  Platform: {train.platform}")
                print()