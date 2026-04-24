from pydantic import BaseModel


class EosCue(BaseModel):
    """Eos lighting cue model."""

    number: float
    label: str | None = None


class EosCueList(BaseModel):
    cues: list[EosCue] = []


class Eos:
    def __init__(self, address='localhost', port=8000, tcp=False) -> None:
        self.address = address
        self.port = port
        self.tcp = tcp

        if self.tcp:
            from pythonosc.tcp_client import SimpleTCPClient

            self.client = SimpleTCPClient(self.address, self.port)
        else:
            from pythonosc.udp_client import SimpleUDPClient

            self.client = SimpleUDPClient(self.address, self.port)

    def send(self, message: str, value: list | int | str | float | None = None):
        if value:
            self.client.send_message(message, value)
        else:
            self.client.send_message(message)
