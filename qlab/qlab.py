from qlab.osc import Client


class QLab:
    def __init__(self, address='localhost', port=53000) -> None:
        self.client = Client(address, port)
        # self.server = Server('127.0.0.1', 51365)

    def send(self, message='/go', value=None) -> dict:
        self.client.send_message(message, value)
        return self.client.get_message()

    def cue(self, cue) -> None:
        self.send('/cue/%s/start' % cue)

    def select(self, select) -> None:
        self.send('/select/%s' % select)

    def get_cue_text(self, cue_no) -> str:
        return self.get_cue_property(cue_no, 'text')

    def get_cue_property(self, cue_no, property) -> any:
        return self.send(f'/cue/{cue_no}/{property}')['data']

    def set_cue_property(self, cue_no, name, value) -> None:
        self.client.send_message('/cue/{cue_no}/{name}'.format(**locals()), value=value)

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

    def go(self) -> None:
        self.send()
