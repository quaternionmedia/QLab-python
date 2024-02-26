from time import sleep

from qlab.osc import Client, Server


class QLab:
    def __init__(self):
        self.client = Client('127.0.0.1', 53000)
        # self.server = Server('127.0.0.1', 51365)

    def send(self, message='/go', value=None):
        sleep(0.01)
        self.client.send_message(message, value)
        # sleep(0.01)
        return self.client.get_message()

    def cue(self, cue):
        self.send('/cue/%s/start' % cue)

    def select(self, select):
        self.send('/select/%s' % select)

    def get_cue_text(self, cue_no):
        return self.get_cue_property(cue_no, 'text')

    def get_cue_property(self, cue_no, property):
        return self.send(f'/cue/{cue_no}/{property}')['data']

    def set_cue_property(self, cue_no, name, value):
        self.client.send_message('/cue/{cue_no}/{name}'.format(**locals()), value=value)

    def select_next_cue(self):
        self.client.send_message('/select/next')
        cue_no = self.get_cue_property('selected', 'number')
        print(cue_no)
        return cue_no

    def select_previous_cue(self):
        self.client.send_message('/select/previous')
        cue_no = self.get_cue_property('selected', 'number')
        print(cue_no)
        return cue_no

    def go(self):
        self.send()
