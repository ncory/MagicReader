from enum import Enum
from ordered_enum import OrderedEnum


class State(Enum):
    Uknown = "unkown"
    Starting = "starting"
    Welcome = "welcome"
    WaitingForTap = "waitingForTap"
    Checking = "checking"
    TapSuccess = "success"
    PlayingSequence = "playingSequence"
    Blackout = "blackout"
    Error = "error"
    Shutdown = "shutdown"


class AppEventType(OrderedEnum):
    ReadRfid = "readRfid"
    EnterWaitMode = "enterWaitMode"
    PlaySequence = "playSequence"
    StopSequence = "stopSequence"
    Blackout = "blackout"
    Shutdown = "shutdown"
#    def __lt__(self, other):
#        if self.__class__ is other.__class__:
#            return self.value < other.value
#        return NotImplemented


class AppEvent():
    def __init__(self, type: AppEventType, data: any = None):
        self.type = type
        self.data = data
    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.type < other.type
        return NotImplemented


class CancelReadException(Exception):
    pass
