class Stats:
    def __init__(self):
        self.total_requests_made: int = 0
        self.completed_requests: int = 0

    @property
    def success_rate(self) -> float:
        return float(self.completed_requests) / float(self.total_requests_made)
