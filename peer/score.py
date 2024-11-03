from peer.configuration import Timeouts, Limits


class Score:
    """
    Holds a record of the last requests outcome.
    The success rate and average duration of a request can be computed by using this class.
    """
    def __init__(self, optimistic: bool = True, history_count: int = Limits.MaxActiveRequests):
        self.count: int = history_count
        self.result_history: list[bool] = [optimistic] * history_count
        self.duration_history: list[float] = [0.0 if optimistic else Timeouts.Request] * history_count

    def update(self, result: bool, duration: float):
        """
        Add result to the history and remove the oldest item.
        """
        self.result_history.pop(0)
        self.result_history.append(result)

        self.duration_history.pop(0)
        self.duration_history.append(duration)

    def success_rate(self) -> float:
        """
        Simply returns the ratio true_values_count / total_values_cunt
        """
        return float(self.result_history.count(True)) / float(self.count)

    def avg_duration(self) -> float:
        """
        Simply returns the average duration
        """
        return sum(dur for dur in self.duration_history) / float(self.count)
