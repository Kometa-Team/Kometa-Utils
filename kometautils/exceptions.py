
class Continue(Exception):
    pass

class Deleted(Exception):
    pass

class Failed(Exception):
    pass

class FilterFailed(Failed):
    pass

class LimitReached(Exception):
    pass

class NonExisting(Exception):
    pass

class NotScheduled(Exception):
    pass

class NotScheduledRange(NotScheduled):
    pass

class TimeoutExpired(Exception):
    pass
