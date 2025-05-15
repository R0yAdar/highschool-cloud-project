""" Creates an IconGenerator single instance which is responsible for 
    storing all of the icons for the filesystem nodes/files/folders 
    according to their extension/type..."""

# Official
from typing import Dict, Union
from enum import Enum

# 3rd Party
import qtawesome as qta
from PyQt6.QtWidgets import QFileIconProvider
from PyQt6.QtGui import QIcon

# Source: https://support.google.com/drive/answer/37603?hl=en
ARCHIVE_FILES = ('zip', 'rar', 'tar', 'gzip')
AUDIO_FORMATS =  ('mp3', 'wav', 'ogg', 'opus')
IMAGE_FILES = ('jpeg', 'jpg', 'png', 'gif', 'bmp', 'tiff', 'svg')
MARKUP_CODE_FILES = ('css', 'html', 'php', 'c', 'cpp', 'h', 'hpp', 'js', 'java', 'py')
VIDEO_FILES = ('mp4', 'mov', 'avi', 'wmv')
LIBRARY_FILES = ('dll', 'lib', 'so')


class IconTypes(Enum):
     Folder = 1
     File = 2
     Video = 3
     Image = 4
     Code = 5
     Audio = 6
     Archive = 7
     Library = 8
     Pdf = 9
     Partial = 10 # In App Specail   

class IconGenerator:
    def __init__(self) -> None:
        pass

    def init(self) -> None:
        # Only After Constructing QApplication
        self.icons: Dict[IconTypes, QIcon] = {}

        self.icons[IconTypes.Folder] = QFileIconProvider().icon(QFileIconProvider.IconType.Folder)
        self.icons[IconTypes.File] = QFileIconProvider().icon(QFileIconProvider.IconType.File)
        self.icons[IconTypes.Video] = qta.icon('mdi.video-image', color='red')
        self.icons[IconTypes.Image] = qta.icon('mdi.image-filter-hdr', color='red')
        self.icons[IconTypes.Code] = qta.icon('mdi.code-braces', color='purple')
        self.icons[IconTypes.Audio] = qta.icon('mdi.music-box', color='green')
        self.icons[IconTypes.Archive] = qta.icon('mdi.archive', color='gray')
        self.icons[IconTypes.Library] = qta.icon('mdi.bookshelf', color='black')
        self.icons[IconTypes.Pdf] = qta.icon('mdi.pdf-box', color='red')
        self.icons[IconTypes.Partial] = qta.icon('ri.file-damage-line', color='red')


        self.lookup_table: Dict[str, IconTypes] = {}

        self.__add_lookup(ARCHIVE_FILES, IconTypes.Archive)
        self.__add_lookup(AUDIO_FORMATS, IconTypes.Audio)
        self.__add_lookup(IMAGE_FILES, IconTypes.Image)
        self.__add_lookup(MARKUP_CODE_FILES, IconTypes.Code)
        self.__add_lookup(VIDEO_FILES, IconTypes.Video)
        self.__add_lookup(LIBRARY_FILES, IconTypes.Library)

        self.lookup_table['pdf'] = IconTypes.Pdf
        self.lookup_table['partial'] = IconTypes.Partial

    def __add_lookup(self, extensions: tuple, what: IconTypes):
        for name in extensions:
            self.lookup_table[name] = what

    def get(self, value: Union[str, IconTypes]) -> QIcon:
        if isinstance(value, IconTypes):
            if result := self.icons.get(value):
                return result
        elif icon_type := self.lookup_table.get(value):
            return self.get(icon_type)
        return self.icons[IconTypes.File]

icon_manager = IconGenerator()