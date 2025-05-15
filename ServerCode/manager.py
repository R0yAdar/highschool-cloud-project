""" Convenience class for managing endpoints for the App/server...
    Flask-style."""
from typing import Callable, Any, Awaitable, Tuple, Union, Literal
from functools import wraps

class Manager():
    ''' Inspired from:
        https://ains.co/blog/things-which-arent-magic-flask-part-1.html
    '''
    def __init__(self) -> None:
        self.routes: dict = {}

    def add_route(self, name :str, requires_auth=True, requires_reader=False):
        def dec(handler):
            self.routes[name] = (handler, requires_auth, requires_reader)
            return handler
        return dec
    
    def serve(self, name: str) -> Tuple[Callable[..., Awaitable], bool, bool]:
        handler = self.routes.get(name)
        if not handler:
            raise ValueError(f"Route '{name}' has not been initialized")
        return handler
    