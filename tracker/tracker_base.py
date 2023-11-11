class TrackerBase:
    def __init__(self, tracker: str):
        self.tracker: str = tracker

    def request_peers(self, torrent_info) -> dict:
        raise NotImplementedError("request_peers not implemented")
