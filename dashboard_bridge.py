"""In-memory connection between the desktop UI and the tracking thread."""
import queue
import threading
import time

class DashboardBridge:
    def __init__(self):
        self.commands = queue.SimpleQueue()
        self.lock = threading.Lock()
        self.controller = None
        self.camera = None
        self.frame = None
        self.sequence = 0
        self.geometry = []
        self.state = {'status':'Connecting to your camera', 'enabled':False}
        self.finished = threading.Event()
        self.updated = time.monotonic()

    def send(self, action, value=None):
        self.commands.put((action,value))

    def drain(self):
        result=[]
        while len(result)<64:
            try: result.append(self.commands.get_nowait())
            except queue.Empty: break
        return result

    def pause(self):
        # Discard pending enable requests, but don't silently lose saved UI settings.
        for action,value in self.drain():
            if action in ('settings','quit'):
                self.send(action,value)
        if self.controller is not None:
            self.controller.disable('PAUSED FROM DASHBOARD')
        self.send('pause')

    def publish(self, frame=None, state=None, geometry=None):
        with self.lock:
            if frame is not None:
                self.frame=frame
                self.sequence+=1
            if state is not None:
                self.state=state.copy()
            if geometry is not None:
                self.geometry=geometry
            self.updated=time.monotonic()

    def snapshot(self):
        with self.lock:
            return self.sequence,self.frame,self.state.copy(),self.updated,self.geometry
