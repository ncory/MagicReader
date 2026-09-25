"""Keeps name resolution off the cue path.

Measured on a reader: an mDNS name that does not answer costs a flat 5 s, and
mDNS has no negative answer to cache, so that is paid again on every call.
Worse, it is not only absent devices - a name whose device is online flaps.
Twelve lookups of a live PiPlayer, two seconds apart, gave six consecutive
5.00 s failures, then 3.10 s, then 0.00 s once avahi had it cached.

The cue path should never wait on that. This resolver keeps a last-known-good
address for every device name the app uses, refreshed on a background thread.
A cue asks for an address and gets an answer immediately or not at all; it
never blocks. While a name is flapping the last good address keeps working,
which is the whole point - the device is usually still there.

Names are kept rather than replaced by fixed IPs on purpose: this is a DHCP
network. A refresh every REFRESH_INTERVAL picks up an address that has moved.

Start it once with start(). Without that the cache stays empty, addressFor()
returns None for everything, and callers fall back to passing the name to the
system resolver exactly as before - degraded, but never broken.
"""
import ipaddress
import socket
import threading
import time


class HostResolver:
    # How often to re-resolve every known name. Also how quickly a device that
    # moved to a new DHCP address is picked up.
    REFRESH_INTERVAL = 60.0

    # How long a last-known-good address is served after its last successful
    # resolution. Long, deliberately: a name that has been flapping for ten
    # minutes is still far more likely to be at its old address than nowhere.
    # A device that has genuinely gone stays unreachable, and the call fails
    # fast at connect rather than slowly at resolution.
    STALE_AFTER = 3600.0

    _entries = {}
    _lock = threading.Lock()
    _thread = None
    _wake = threading.Event()
    _running = False

    # --- registration ----------------------------------------------------
    @staticmethod
    def isAddressLiteral(host):
        """True for 192.168.1.135 and the like, which need no resolving."""
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    @staticmethod
    def register(host):
        """Notes a name so the background thread keeps it fresh. Cheap."""
        if not isinstance(host, str):
            return False
        host = host.strip().lower()
        if not host or HostResolver.isAddressLiteral(host):
            return False
        with HostResolver._lock:
            if host not in HostResolver._entries:
                HostResolver._entries[host] = {"ip": None, "at": 0.0, "failures": 0}
                new = True
            else:
                new = False
        if new:
            # Resolve it on the next loop rather than waiting out the interval
            HostResolver._wake.set()
        return new

    @staticmethod
    def primeFrom(hosts):
        """Registers a batch of names, e.g. everything the config mentions."""
        count = 0
        for host in hosts or ():
            if HostResolver.register(host):
                count += 1
        return count

    # --- lookup ----------------------------------------------------------
    @staticmethod
    def addressFor(host):
        """Last-known-good address for a name, or None. Never blocks."""
        if not isinstance(host, str):
            return None
        host = host.strip().lower()
        if not host or HostResolver.isAddressLiteral(host):
            return None
        with HostResolver._lock:
            entry = HostResolver._entries.get(host)
            if entry is None:
                # First time this name has been seen. Register it so the next
                # cue can be served from cache, and let this one through.
                HostResolver._entries[host] = {"ip": None, "at": 0.0, "failures": 0}
                HostResolver._wake.set()
                return None
            if entry["ip"] is None:
                return None
            if time.monotonic() - entry["at"] > HostResolver.STALE_AFTER:
                return None
            return entry["ip"]

    @staticmethod
    def substitute(url):
        """Swaps a resolvable name in a URL for its cached address.

        Returns (url, host) where host is the original name when it was
        substituted, so the caller can still send a correct Host header, or
        None when the URL was left alone.
        """
        if not isinstance(url, str) or "//" not in url:
            return url, None
        try:
            scheme, rest = url.split("//", 1)
            authority, _, tail = rest.partition("/")
        except ValueError:
            return url, None
        if "@" in authority:
            # Credentials in the authority: not something this app produces,
            # and rewriting it correctly is not worth the risk
            return url, None
        host, colon, port = authority.partition(":")
        ip = HostResolver.addressFor(host)
        if ip is None:
            return url, None
        newAuthority = f"{ip}{colon}{port}" if colon else ip
        return f"{scheme}//{newAuthority}" + (f"/{tail}" if tail or url.endswith("/") else ""), authority

    # --- refreshing ------------------------------------------------------
    @staticmethod
    def refreshOnce():
        """Resolves every known name once. Blocks - for the thread and tests."""
        with HostResolver._lock:
            hosts = list(HostResolver._entries)
        for host in hosts:
            try:
                ip = socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]
            except Exception:
                ip = None
            with HostResolver._lock:
                entry = HostResolver._entries.get(host)
                if entry is None:
                    continue
                if ip is not None:
                    changed = entry["ip"] != ip
                    if changed:
                        was = entry["ip"]
                        print(f"Resolved {host} -> {ip}"
                              + (f" (was {was})" if was else ""), flush=True)
                    entry["ip"] = ip
                    entry["at"] = time.monotonic()
                    entry["failures"] = 0
                else:
                    entry["failures"] += 1
                    # Say so once, not on every sweep, and only while we have
                    # nothing to fall back on
                    if entry["failures"] == 1 and entry["ip"] is None:
                        print(f"Could not resolve {host} - cues to it will wait "
                              "on the system resolver until it answers", flush=True)

    @staticmethod
    def _run():
        while HostResolver._running:
            HostResolver.refreshOnce()
            HostResolver._wake.wait(HostResolver.REFRESH_INTERVAL)
            HostResolver._wake.clear()

    @staticmethod
    def start():
        """Starts the background refresher. Idempotent."""
        with HostResolver._lock:
            if HostResolver._thread is not None and HostResolver._thread.is_alive():
                return False
            HostResolver._running = True
            HostResolver._wake.clear()
            HostResolver._thread = threading.Thread(
                target=HostResolver._run, name="HostResolver", daemon=True)
            HostResolver._thread.start()
        return True

    @staticmethod
    def stop(timeout: float = 2.0):
        with HostResolver._lock:
            HostResolver._running = False
            thread = HostResolver._thread
            HostResolver._thread = None
        HostResolver._wake.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout)

    @staticmethod
    def reset():
        """Forgets every name. For tests."""
        HostResolver.stop()
        with HostResolver._lock:
            HostResolver._entries.clear()

    @staticmethod
    def snapshot():
        """A copy of what is cached, for the API and for tests."""
        with HostResolver._lock:
            return {h: dict(e) for h, e in HostResolver._entries.items()}
