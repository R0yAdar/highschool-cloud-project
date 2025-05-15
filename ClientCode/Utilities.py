from PyQt6 import QtWidgets, QtCore
from typing import Callable
from contextlib import contextmanager
from dataclasses import dataclass
import math

def get_lowercase_extension(s: str) -> str:
    return s.split('.')[-1].lower()

def convert_size(size_bytes):
   '''Utility function for converting a size in bytes
      into a human readable format.'''
   if size_bytes == 0:
       return "0B"
   size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return "%s %s" % (s, size_name[i])

@dataclass
class ErrorDisplay:
    title: str
    information: str

class HashException(Exception):
    pass

class ServerFailure(Exception):
    pass

@contextmanager
def wait_cursor():
    '''Inspired From: 
                        #https://stackoverflow.com/questions/8218900/how-can-i-change-the-cursor-shape-with-pyqt'''
    try:
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        yield
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()

@contextmanager
def error_resolver(resolver: Callable[[ErrorDisplay], None]):
    try:
        yield
    except TimeoutError:
        resolver(ErrorDisplay("Timeout", "Realy Slow Internet or Server Failure"))
    except ConnectionError:
        resolver(ErrorDisplay("Internet Problem", "Couldn't Communicate With Server"))
    except HashException:
        resolver(ErrorDisplay("Hash Validation Error", "The Downloaded File's Hash Isn't Matching"))
    except ServerFailure:
        resolver(ErrorDisplay("Server Failed", "Couldn't Handle Your Request"))
