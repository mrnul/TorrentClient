from peer.configuration import Punishments


class Score:
    """
    Simply holds a list of bool values and counts the ratio of true_values_count / len(list).
    Each time update is called the new value is added to the list and the oldest value is removed.
    The purpose of this class is to figure out the punishment of peers depending on success rate
    """
    def __init__(self, optimistic: bool = True, history_count: int = 10):
        self.count: int = history_count
        self.history_record: list[bool] = [optimistic] * history_count

    def update(self, result: bool) -> float:
        """
        Add result to the history and remove the oldest item.
        Returns the new score
        """
        self.history_record.pop(0)
        self.history_record.append(result)
        return self.calculate()

    def calculate(self) -> float:
        """
        Simply returns the ratio true_values_count / total_values_cunt
        """
        return float(self.history_record.count(True)) / float(self.count)

    def get_punishment_duration(self) -> float:
        """
        The punishment is the amount of seconds a peer should sleep.
        Returns a value in [0.0, Punishments.Request] depending on current score.
        """
        current_error_score: float = 1.0 - self.calculate()
        return Punishments.Request * current_error_score
