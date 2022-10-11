from genericpath import isfile
from typing import Union
import configparser
from pathlib import Path
import os


class Config:
    def __init__(self, config_file: Union[str, Path]):
        """
        Loads up the config saved for the bot

        Args:
            config_file (Union[str, Path]): _description_
        """

        self._config_file = config_file
        if not os.path.isfile(config_file):
            self._create_new_config()
        
        self._data = self._read_config()

    def _create_new_config(self):
        config = configparser.ConfigParser()
        config['DEFAULT'] = {
            'AutoSelectSong': True
        }
        
        with open(self._config_file, 'w') as cf:
            config.write(cf)

    def _read_config(self):
        config = configparser.ConfigParser()
        config.read(self._config_file)
        return config

    def _write_to_config(self, id_:int ):
        config = configparser.ConfigParser()
        config.read(self._config_file)
        config.add_section(str(id_))
        config.set(str(id_), 'AutoSelectSong', "True")
        with open(self._config_file, 'w') as cf:
            config.write(cf)

    def isAutoPick(self, id_: int):
        if str(id_) not in self._data:
            self._write_to_config(id_)
            self._data = self._read_config()
        return self._data[str(id_)].getboolean('AutoSelectSong')

    def set_state(self, id_:int):
        if str(id_) not in self._data:
            self._write_to_config(id_)
            self._data = self._read_config()
        if self.isAutoPick(id_):
            self._data[str(id_)]['AutoSelectSong'] = "False"
        else:
            self._data[str(id_)]['AutoSelectSong'] = "True"
        
        with open(self._config_file, 'w') as cf:
            self._data.write(cf)