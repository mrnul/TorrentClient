class TrackerBase:
    def __init__(self, tracker: str):
        self.tracker: str = tracker

    def request_peers(self, torrent_decoded_data: dict, self_id: bytes, port: int) -> dict:
        raise NotImplementedError("request_peers not implemented")
