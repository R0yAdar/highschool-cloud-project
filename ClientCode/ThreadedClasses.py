""" This Module includes a lot of helpful QThread overrides that implement 
    custom behaviour that performs a blocking network action without blocking
    the main thread, while emitting signals to show its progress/errors/etc..."""

# Official
from typing import Dict, List
from dataclasses import dataclass
import queue

# 3rd Party
from PyQt6 import QtCore

# Mine
from Utilities import error_resolver, ErrorDisplay
from Requests import Requests
import RAP

@dataclass
class FileUploadInfo:
    path: str
    size: int

class FileDownloadThread(QtCore.QThread):
    done = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int)
    failed = QtCore.pyqtSignal(ErrorDisplay)
    _is_running = True

    def __init__(self, user: Requests, where: str, what: RAP.FileInfo, start=0, end=0) -> None:
        super().__init__()
        self.user = user
        self.file = what
        self.where = where
        self.st = start
        self.end = end

    def run(self) -> None:
        total = 0
        if self.st < self.end:
            total_size = self.end - self.st
        else:
            total_size = self.file.size
        with error_resolver(self.failed.emit):
            for n in self.user.DownloadFile(download_path=self.where, file=self.file, start=self.st, end=self.end):
                if not self._is_running:
                    break
                if isinstance(n, int):
                    total += n
                    self.progress.emit(int(total/total_size*100))
                else:
                    break
        self.done.emit()
    def stop(self):
        self._is_running = False

class MultiFileUploadThread(QtCore.QThread):
    done = QtCore.pyqtSignal()
    current_file = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int)
    failed = QtCore.pyqtSignal(ErrorDisplay)
    _is_running = True

    def __init__(self, user: Requests, filelist: List[FileUploadInfo], where: RAP.DirInfo) -> None:
        super().__init__()
        self.user = user
        self.filelist = filelist
        self.where = where
    
    def run(self) -> None:
        with error_resolver(self.failed.emit):
            for file in self.filelist:
                total = 0
                self.progress.emit(total)
                self.current_file.emit(file.path)
                for n in self.user.UploadFile(file.path, file.size, where=self.where):
                    if not self._is_running: return
                    if isinstance(n, int):
                        total += n
                        self.progress.emit(int(total/file.size*100))
        self.done.emit()

    def stop(self) -> None:
        self._is_running = False


class FileUploadThread(QtCore.QThread):
    done = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int)
    failed = QtCore.pyqtSignal(str)
    _is_running = True

    def __init__(self, user: Requests, file: str, where: RAP.DirInfo, size) -> None:
        super().__init__()
        self.user = user
        self.file = file
        self.where = where
        self.size = size

    def run(self) -> None:
        total = 0
        with error_resolver(self.failed.emit):
            for n in self.user.UploadFile(self.file, self.size, where=self.where):
                if not self._is_running:
                    return
                if isinstance(n, int):
                    total += n
                    self.progress.emit(int(total/self.size*100))
                else:
                    break
        self.done.emit()
        
    def stop(self):
        self._is_running = False

class NodeMovingThread(QtCore.QThread):
    done = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int)
    failed = QtCore.pyqtSignal(ErrorDisplay)
    _is_running = True

    def __init__(self, user: Requests, node_ids: list, to_id) -> None:
        super().__init__()
        self.user = user
        self.node_ids = node_ids
        self.to_id = to_id

    def run(self) -> None:
        with error_resolver(self.failed.emit):
            for count, id in enumerate(self.node_ids):
                if not self._is_running:
                    break
                self.user.MoveNode(id, self.to_id)
                self.progress.emit(count)
        self.done.emit()

    def stop(self):
        self._is_running = False

class NodeCopyingThread(QtCore.QThread):
    done = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int)
    failed = QtCore.pyqtSignal(ErrorDisplay)
    _is_running = True

    def __init__(self, user: Requests, node_ids: list, to_id) -> None:
        super().__init__()
        self.user = user
        self.node_ids = node_ids
        self.to_id = to_id

    def run(self) -> None:
        with error_resolver(self.failed.emit):
            for count, id in enumerate(self.node_ids):
                if not self._is_running:
                    break
                self.user.CopyNode(id, self.to_id)
                self.progress.emit(count)
        self.done.emit()

    def stop(self):
        self._is_running = False

class NodeDeletingThread(QtCore.QThread):
    done = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int)
    failed = QtCore.pyqtSignal(ErrorDisplay)
    _is_running = True

    def __init__(self, user: Requests, node_ids: list) -> None:
        super().__init__()
        self.user = user
        self.node_ids = node_ids

    def run(self) -> None:
        with error_resolver(self.failed.emit):
            for count, id in enumerate(self.node_ids):
                if not self._is_running:
                    break
                self.user.DeleteNode(id)
                self.progress.emit(count)
        self.done.emit()

    def stop(self):
        self._is_running = False


class AlternativeIconThread(QtCore.QThread):
    tasks: queue.LifoQueue['AlternativeIconRunnable']  = queue.LifoQueue()
    error = QtCore.pyqtSignal(ErrorDisplay)

    def __init__(self, user: Requests, parent=None) -> None:
        super().__init__(parent)
        self.user = user
        self._running = True

    def run(self, maxchunk=12) -> None:
        while self._running:
            gathered: List[AlternativeIconRunnable] = []
            for i in range(maxchunk):
                try:
                    task = self.tasks.get_nowait()
                    if not task.finished():
                        gathered.append(task)
                except queue.Empty:
                    break 
            request = RAP.PipelinedRequest()            
            for task in gathered:
                request.requests.append(RAP.Request(get_icon=RAP.GetIco(RAP.FileInfo(id=task.file_id))))
            with error_resolver(lambda x: None): #!
                for (task, response) in zip(gathered, self.user.Pipeline(request, RAP.IcoResponse)):
                    task.complete(response)
    
    def submit(self, task: 'AlternativeIconRunnable'):
        self.tasks.put_nowait(task)
    
    def stop(self):
        self._running = False

class AlternativeIconRunnable:
    cached_icons: Dict[int, bytes] = {}    
    def __init__(self, file_id) -> None:
        super().__init__()
        self.signals = self.Signals()
        self.file_id = file_id      
    
    def finished(self):
        if self.file_id in AlternativeIconRunnable.cached_icons:
            self.signals.achieved.emit(AlternativeIconRunnable.cached_icons[self.file_id])
            return True
        return False
        
    def complete(self, answer: RAP.IcoResponse):
        if answer.response.status == RAP.BasicResponseSTATUS.FAILED:
            return
        image = answer.image
        AlternativeIconRunnable.cached_icons[self.file_id] = image
        try:
            self.signals.achieved.emit(image)
        except RuntimeError:
            pass

    class Signals(QtCore.QObject):
        achieved = QtCore.pyqtSignal(bytes)

class AsyncBlockingAction(QtCore.QThread):
    done = QtCore.pyqtSignal()
    failed = QtCore.pyqtSignal(ErrorDisplay)
    _is_running = True

    def __init__(self, action,*args) -> None:
        super().__init__()
        self.action = action
        self.args = args

    def run(self) -> None:
        with error_resolver(self.failed.emit):
           self.action(*self.args)
        self.done.emit()

    def stop(self):
        self._is_running = False
