from peer.configuration import Punishments


class Score:
    def __init__(self, optimistic: bool = True, history_count: int = 5):
        self.count: int = history_count
        self.history_record: list[bool] = [optimistic] * history_count

    def update(self, result: bool) -> float:
        self.history_record.pop(0)
        self.history_record.append(result)
        return self.calculate()

    def calculate(self) -> float:
        return float(self.history_record.count(True)) / float(self.count)

    def get_punishment_duration(self) -> float:
        current_error_score: float = 1.0 - self.calculate()
        return Punishments.Request * current_error_score
