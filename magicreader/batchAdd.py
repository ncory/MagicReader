"""Batch-add mode for the Bands page.

While it is on, every tap is captured instead of playing a sequence: a band
the reader does not know yet is saved straight away with its ID as its
nickname and no sequences, and one it already knows is left alone. The page
polls for what was read and ends the mode with Done.

The mode ends on its own if the page stops polling, so a closed tab or a
sleeping laptop cannot leave the reader swallowing every tap.
"""
import threading
import time


class BatchAdd:
    IDLE_TIMEOUT_SECONDS = 30

    def __init__(self, band_manager):
        self.band_manager = band_manager
        self.lock = threading.Lock()
        self.active = False
        self.reads = []
        self.lastPoll = 0.0

    def start(self):
        with self.lock:
            self.active = True
            self.reads = []
            self.lastPoll = time.monotonic()
        print("Batch add started", flush=True)

    def stop(self):
        with self.lock:
            wasActive = self.active
            self.active = False
        if wasActive:
            print("Batch add stopped", flush=True)

    def isActive(self) -> bool:
        with self.lock:
            if self.active and time.monotonic() - self.lastPoll > BatchAdd.IDLE_TIMEOUT_SECONDS:
                self.active = False
                print("Batch add ended - the page stopped checking in", flush=True)
            return self.active

    def capture(self, band_id: str, isDisney: bool = False) -> dict:
        """Records a tap, saving the band if it is new. Returns the read as the page sees it."""
        band_id = str(band_id)
        existing = self.band_manager.bands.get(band_id)
        if isinstance(existing, dict):
            entry = {"id": band_id, "status": "known", "name": existing.get("name") or band_id}
        else:
            self.band_manager.updateBand(band_id, band_id, [])
            saved = self.band_manager.saveToFile()
            entry = {"id": band_id, "status": "added" if saved else "error", "name": band_id}
        entry["isDisney"] = bool(isDisney)
        with self.lock:
            entry["seq"] = len(self.reads) + 1
            self.reads.append(entry)
        print(f"Batch add: {band_id} {entry['status']}", flush=True)
        return entry

    def poll(self, after: int = 0) -> dict:
        """The reads after sequence number `after`. Also keeps the mode alive."""
        active = self.isActive()
        with self.lock:
            if active:
                self.lastPoll = time.monotonic()
            reads = [read for read in self.reads if read["seq"] > after]
        return {"active": active, "reads": reads}
