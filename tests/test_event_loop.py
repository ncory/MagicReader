"""The event loop survives a handler that raises.

runEventQueue had no exception guard. One raise killed the thread outright and
the app went on reporting a healthy state over the API while silently ignoring
every tap - the worst kind of failure, because nothing looks wrong.

MagicBand.__init__ probes real hardware, so these tests build an instance with
__new__ and set only the attributes the loop touches.
"""
import queue
import threading
import unittest

import _support  # noqa: F401
import magicreader
from helpers import AppEvent, AppEventType, State


def makeApp():
    app = magicreader.MagicBand.__new__(magicreader.MagicBand)
    app.event_queue = queue.PriorityQueue()
    app.is_active = True
    app.allowRead = False
    app.read_once_enabled = False
    app.read_once_result = None
    app.sequence_lock = threading.Lock()
    app.active_sequence = None
    app.active_sequence_id = None
    app.sequence_cancel_event = None
    app.sequence_thread = None
    app.pending_rfid_after_sequence_cancel = None
    app.inactive_timer = None
    app.state = State.WaitingForTap
    app.status = None
    app.isError = False
    # Neutralise everything the loop calls that would touch hardware or timers
    app.resetInactiveTimer = lambda: None
    app.startWaitModeTimer = lambda *a, **k: None
    app.triggerError = lambda: None
    app.triggerWaiting = lambda: None
    app.triggerBlackout = lambda: None
    app.soundManager = type("S", (), {
        "stopAllSounds": staticmethod(lambda: None),
        "stopMusic": staticmethod(lambda: None),
    })()
    return app


class EventLoopGuardTests(unittest.TestCase):
    def tearDown(self):
        if getattr(self, "app", None) is not None:
            self.app.is_active = False

    def test_loop_survives_a_raising_handler_and_keeps_processing(self):
        self.app = app = makeApp()
        raised = []
        handled = []

        def explode():
            raised.append(1)
            raise RuntimeError("simulated failure inside a handler")

        app.triggerBlackout = explode
        app.triggerWaiting = lambda: handled.append(1)

        thread = threading.Thread(target=app.runEventQueue, daemon=True)
        thread.start()
        try:
            for _ in range(3):
                app.event_queue.put((2, AppEvent(AppEventType.Blackout, False)))
            threading.Event().wait(0.5)
            self.assertEqual(len(raised), 3, "not every event reached the handler")
            self.assertTrue(thread.is_alive(), "the event thread died on an exception")

            # And it still handles what comes next
            app.event_queue.put((2, AppEvent(AppEventType.EnterWaitMode)))
            threading.Event().wait(0.5)
            self.assertEqual(len(handled), 1, "loop stopped processing after the failures")
            self.assertEqual(app.state, State.WaitingForTap)
        finally:
            app.is_active = False

    def test_a_failing_shutdown_still_ends_the_thread(self):
        # Otherwise waitForShutdown() would block until its timeout on every
        # stop, because the guard would swallow the failure and loop forever.
        self.app = app = makeApp()
        app.cleanup = lambda: (_ for _ in ()).throw(RuntimeError("cleanup blew up"))
        app.cancelActiveSequence = lambda: False

        thread = threading.Thread(target=app.runEventQueue, daemon=True)
        thread.start()
        app.event_queue.put((1, AppEvent(AppEventType.Shutdown)))
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), "thread kept running after a failed shutdown")


if __name__ == "__main__":
    unittest.main()
