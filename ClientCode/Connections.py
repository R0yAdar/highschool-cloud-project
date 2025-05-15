""" Module for implementing a basic reuseable and reimplementable simple
    API for managing connections and TLS streams bewteen a defined HOST 
    to this client. """

import socket
import ssl
from queue import Queue
socket.setdefaulttimeout(7)
HOSTNAME, PORT = "127.0.0.1", 12345

class SSLStream:
    def __init__(self):
        self.context = ssl.create_default_context()
        sock = socket.create_connection((HOSTNAME, PORT))
        self.socket = self.context.wrap_socket(sock, server_hostname=HOSTNAME)
        
    def send(self, data: bytes) -> int:
        return self.socket.send(data)

    def write(self, data: bytes) -> None:
        self.socket.sendall(data)
    
    def read(self, amount: int) -> bytes:
        return self.socket.recv(amount)

    def readexactly(self, amount: int) -> bytes:
        buff = bytearray(amount)
        pos = 0
        while pos < amount:
            cr = self.socket.recv_into(memoryview(buff)[pos:])
            if cr == 0:
                raise ConnectionError('Connection Closed')
            pos += cr
        return buff
    
    def close(self):
        self.socket.close()

class SSLStreamFactory:
    def __init__(self) -> None:
        self.recycle: Queue = Queue()

    def get(self) -> SSLStream:
        stream = SSLStream()        
        return stream
    
    def ret(self, stream: SSLStream):
        stream.close()
    
    def clear(self):
        while not self.recycle.empty():
            stream = self.recycle.get()
            stream.close()
