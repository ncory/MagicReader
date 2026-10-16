#!/usr/bin/env python3
"""Reads the same bands on the MFRC522 and on a PC/SC reader and compares UIDs.

Tap a band on one reader, then the other. Each read is printed as it happens;
when both readers have read a band within --window seconds of each other the
two UIDs are compared and the result printed as MATCH or MISMATCH. Ctrl-C
prints a summary of every band seen.

Each read also shows "id": the band ID as the MagicReader app stores it, ready
to paste into the Bands page.

The MagicReader service must be stopped first: spidev lets two processes open
the chip at once and they would corrupt each other's exchanges.

    sudo systemctl stop MagicReader.service
    ~/rfid-compare/.venv/bin/python compare-readers.py

The PC/SC side needs pcscd running and pyscard installed. The ACS reader is
asked for its UID with the standard PC/SC "Get Data" APDU (FF CA 00 00 00).
"""
import argparse
import csv
import datetime
import os
import queue
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "magicreader")]

from mfrc522Uid import Mfrc522Uid, NoTag, ReadError, describeSak  # noqa: E402

GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]

# PC/SC Part 3 card names, from the ATR a reader synthesises for storage cards.
PCSC_CARD_NAMES = {
    0x0001: "MIFARE Classic 1K",
    0x0002: "MIFARE Classic 4K",
    0x0003: "MIFARE Ultralight / NTAG",
    0x0026: "MIFARE Mini",
    0x003A: "MIFARE Ultralight C",
}


def describeAtr(atr) -> str:
    atr = list(atr)
    # 3B 8F 80 01 80 4F 0C A0 00 00 03 06 SS C0 C1 00 00 00 00 TCK
    if len(atr) >= 15 and atr[4:12] == [0x80, 0x4F, 0x0C, 0xA0, 0x00, 0x00, 0x03, 0x06]:
        name = (atr[13] << 8) | atr[14]
        return PCSC_CARD_NAMES.get(name, f"PC/SC card name 0x{name:04X}")
    if len(atr) >= 4 and atr[0] == 0x3B and atr[2:4] == [0x80, 0x01]:
        return "ISO 14443-4"
    return "unknown"


class Read:
    def __init__(self, source, uid, **extra):
        self.time = datetime.datetime.now()
        self.source = source
        self.uid = bytes(uid)
        self.extra = extra

    @property
    def uidHex(self):
        return self.uid.hex(" ").upper()

    @property
    def appId(self):
        # Same format as RfidMfrc522.runReaderThread()
        return self.uid.hex().upper()


def otherMagicReaderRunning():
    me = os.getpid()
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == me:
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "magicreader/__main__.py" in cmdline:
            return int(pid)
    return None


# --- readers ------------------------------------------------------------------

def runMfrc522(args, events, stop):
    try:
        reader = Mfrc522Uid(resetPin=args.reset_pin, rxGainDb=args.gain)
    except Exception as e:
        events.put(("error", f"MFRC522 failed to start: {e}"))
        return
    version = reader.version()
    events.put(("info", f"MFRC522 ready, VersionReg=0x{version:02X}"
                        + (f", RX gain {args.gain} dB" if args.gain else "")))
    errors = 0
    try:
        while not stop.is_set():
            try:
                tag = reader.readTag(halt=True)
            except NoTag:
                time.sleep(0.03)
                continue
            except ReadError as e:
                errors += 1
                if args.verbose:
                    events.put(("info", f"MFRC522 read error #{errors}: {e}"))
                time.sleep(0.03)
                continue
            events.put(("read", Read("MFRC522", tag.uid,
                                     atqa=tag.atqa.hex().upper(),
                                     sak=f"{tag.sak:02X}",
                                     hint=describeSak(tag.sak))))
    finally:
        reader.close()
        events.put(("info", f"MFRC522 stopped ({errors} partial reads discarded)"))


def startPcsc(args, events):
    try:
        from smartcard.CardMonitoring import CardMonitor, CardObserver
        from smartcard.System import readers
        from smartcard.util import toHexString
    except ImportError:
        events.put(("error", "pyscard is not installed (pip install pyscard) - or run with --no-acs"))
        return None

    def useReader(name):
        # ACS readers also list a SAM slot - a socket for a secure module
        # inside the reader, not the contactless field - so skip it.
        name = str(name).lower()
        return args.acs_reader.lower() in name and "sam" not in name

    try:
        names = [str(r) for r in readers()]
    except Exception as e:
        events.put(("error", f"PC/SC unavailable ({e}) - is pcscd running?"))
        return None
    events.put(("info", "PC/SC readers: " + (", ".join(names) or "none")))
    chosen = [n for n in names if useReader(n)]
    if not chosen:
        events.put(("error", f"no PC/SC reader matching '{args.acs_reader}'"))
        return None
    events.put(("info", "Using: " + ", ".join(chosen)))

    class Observer(CardObserver):
        def update(self, observable, handlers):
            added, _removed = handlers
            for card in added:
                if not useReader(card.reader):
                    continue
                try:
                    conn = card.createConnection()
                    conn.connect()
                    data, sw1, sw2 = conn.transmit(GET_UID_APDU)
                    conn.disconnect()
                except Exception as e:
                    events.put(("info", f"ACS read failed: {e}"))
                    continue
                if (sw1, sw2) != (0x90, 0x00):
                    events.put(("info", f"ACS Get UID returned SW {sw1:02X}{sw2:02X}"))
                    continue
                events.put(("read", Read("ACS", data,
                                         atr=toHexString(card.atr).replace(" ", ""),
                                         hint=describeAtr(card.atr))))

    monitor = CardMonitor()
    observer = Observer()
    monitor.addObserver(observer)
    return monitor, observer


# --- main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--window", type=float, default=15,
                        help="seconds between the two taps that still count as the same band (default 15)")
    parser.add_argument("--log", default=os.path.expanduser("~/rfid-compare/reads.csv"),
                        help="CSV file every read is appended to")
    parser.add_argument("--acs-reader", default="ACR1555",
                        help="substring of the PC/SC reader name to use (default ACR1555)")
    parser.add_argument("--no-acs", action="store_true", help="MFRC522 only")
    parser.add_argument("--no-mfrc522", action="store_true", help="PC/SC reader only")
    parser.add_argument("--reset-pin", type=int, default=22,
                        help="BOARD pin wired to the MFRC522 RST line (default 22, as in the app)")
    parser.add_argument("--gain", type=int, choices=[18, 23, 33, 38, 43, 48],
                        help="MFRC522 receiver gain in dB (chip default 33)")
    parser.add_argument("--force", action="store_true",
                        help="run even though the MagicReader app appears to be running")
    parser.add_argument("-v", "--verbose", action="store_true", help="show partial MFRC522 reads")
    args = parser.parse_args()

    if not args.no_mfrc522:
        pid = otherMagicReaderRunning()
        if pid and not args.force:
            sys.exit(f"MagicReader is running (pid {pid}) and owns the MFRC522.\n"
                     "Stop it first:  sudo systemctl stop MagicReader.service")

    events = queue.Queue()
    stop = threading.Event()
    pcsc = None
    if not args.no_acs:
        pcsc = startPcsc(args, events)
    if not args.no_mfrc522:
        threading.Thread(target=runMfrc522, args=(args, events, stop), daemon=True).start()

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    newLog = not os.path.exists(args.log)
    logFile = open(args.log, "a", newline="")
    log = csv.writer(logFile)
    if newLog:
        log.writerow(["time", "source", "uid", "uid_len", "app_id", "atqa", "sak", "atr", "hint", "result"])

    last = {}        # source -> most recent Read
    seen = {}        # uid -> {"MFRC522": n, "ACS": n, "hint": str}
    mismatches = []

    print("Tap a band on one reader, then the other. Ctrl-C to finish.\n", flush=True)
    try:
        while True:
            try:
                kind, payload = events.get(timeout=0.5)
            except queue.Empty:
                continue
            if kind != "read":
                print(("ERROR: " if kind == "error" else "") + payload, flush=True)
                continue

            read = payload
            other = last.get("ACS" if read.source == "MFRC522" else "MFRC522")
            last[read.source] = read

            stats = seen.setdefault(read.uid, {"MFRC522": 0, "ACS": 0, "hint": ""})
            stats[read.source] += 1
            if read.source == "MFRC522":
                stats["hint"] = read.extra.get("hint", "")

            result = ""
            if other and (read.time - other.time).total_seconds() <= args.window:
                if other.uid == read.uid:
                    result = "MATCH"
                else:
                    result = "MISMATCH"
                    mismatches.append((other, read))
                # Each read pairs at most once - forget both halves, or the
                # next band tapped on the first reader is compared with this one.
                last.pop(other.source)
                last.pop(read.source)

            line = (f"{read.time:%H:%M:%S}  {read.source:<7}  {read.uidHex:<29} ({len(read.uid)} bytes)"
                    f"  id={read.appId}")
            if read.source == "MFRC522":
                line += f"  SAK={read.extra['sak']}  {read.extra['hint']}"
            else:
                line += f"  {read.extra['hint']}"
            print(line, flush=True)
            if result == "MATCH":
                print("          MATCH - both readers agree\n", flush=True)
            elif result == "MISMATCH":
                print(f"          MISMATCH - {other.source} read {other.uidHex}\n", flush=True)

            log.writerow([read.time.isoformat(timespec="seconds"), read.source, read.uid.hex().upper(),
                          len(read.uid), read.appId, read.extra.get("atqa", ""),
                          read.extra.get("sak", ""), read.extra.get("atr", ""),
                          read.extra.get("hint", ""), result])
            logFile.flush()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if pcsc:
            pcsc[0].deleteObserver(pcsc[1])
        time.sleep(0.2)
        while not events.empty():
            kind, payload = events.get()
            if kind != "read":
                print(payload)
        logFile.close()

    printSummary(seen, mismatches, args.log)


def printSummary(seen, mismatches, logPath):
    print("\n" + "=" * 100)
    print(f"{'band id':<22} {'len':>3}  {'MFRC522':>7}  {'ACS':>3}  type (from MFRC522 SAK)")
    print("-" * 100)
    for uid, s in seen.items():
        print(f"{uid.hex().upper():<22} {len(uid):>3}  {s['MFRC522']:>7}  {s['ACS']:>3}  {s['hint']}")
    print("=" * 100)

    for a, b in mismatches:
        print(f"MISMATCH: {a.source} {a.uidHex} vs {b.source} {b.uidHex} at {b.time:%H:%M:%S}")
    if not mismatches:
        print("No mismatches this session.")
    print(f"Every read is in {logPath}")


if __name__ == "__main__":
    main()
