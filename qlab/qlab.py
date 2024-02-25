from qlab.osc import Client, Server


class QLab:
    def __init__(self):
        self.client = Client('127.0.0.1', 53000)
        # self.server = Server('127.0.0.1', 51365)

    def send(self, message='/go', value=None):
        self.client.send_message(message, value)
        return self.client.get_message()

    def cue(self, cue):
        self.send('/cue/%s/start' % cue)

    def select(self, select):
        self.send('/select/%s' % select)

    def get_cue_text(self, cue_no):
        return self.get_cue_property(cue_no, 'text')

    def get_cue_property(self, cue_no, name):
        self.client.send_message('/cue/{cue_no}/{name}'.format(**locals()))
        response = self.client.get_message()
        if response:
            return response.get('data')

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
