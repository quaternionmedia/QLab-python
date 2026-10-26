import time
from contextlib import suppress
from socket import SHUT_RDWR

from qlab.osc import Client

# shortcut: QLab drops a request identical to the one before it if it arrives under ~0.1 s after;
# a fixed wait before repeating one, upgrade if QLab's window is measured
DUPLICATE_GAP = 0.2  # seconds


class QLab:
    def __init__(self, address='localhost', port=53000) -> None:
        self.client = Client(address, port)
        self.last = None  # (message, value) of the last request
        # self.server = Server('127.0.0.1', 51365)
        self.send('/alwaysReply', 1)

    def send(self, message='/go', value=None) -> dict:
        # Shared by threads: one request and its reply at a time
        with self.client.lock:
            if (message, value) == self.last:
                time.sleep(DUPLICATE_GAP)
            self.last = (message, value)
            try:
                if self.client.fresh:
                    self.client.send_message('/alwaysReply', 1)
                    self.client.get_message()
                    self.client.fresh = False
                self.client.send_message(message, value)
                return self.client.get_message()
            except OSError:  # timed out or dropped: a late reply must not answer the next request
                self.client.reconnect()
                raise

    def cue(self, cue) -> None:
        self.send('/cue/%s/start' % cue)

    def select(self, select) -> None:
        self.send('/select/%s' % select)

    def get_cue_text(self, cue_no) -> str:
        return self.get_cue_property(cue_no, 'text')

    def get_cue_property(self, cue_no, property) -> any:
        return self.send(f'/cue/{cue_no}/{property}')['data']

    def set_cue_property(self, cue_no, name, value) -> None:
        self.client.send_message(f'/cue/{cue_no}/{name}', value=value)

    def select_next_cue(self) -> str:
        self.client.send_message('/select/next')
        cue_no = self.get_cue_property('selected', 'number')
        print(cue_no)
        return cue_no

    def select_previous_cue(self) -> str:
        self.client.send_message('/select/previous')
        cue_no = self.get_cue_property('selected', 'number')
        print(cue_no)
        return cue_no

    def network_patches(self) -> list[dict]:
        """The workspace's network patches as ``{uniqueID, name}``. Patch N is the Nth entry (1-based)."""
        return self.send('/settings/network/patchList')['data']

    def go(self) -> None:
        self.send()

    def close(self) -> None:
        # shutdown wakes a send that is waiting for its reply; close alone does not
        with suppress(OSError):  # already disconnected
            self.client.conn.shutdown(SHUT_RDWR)
        self.client.conn.close()
