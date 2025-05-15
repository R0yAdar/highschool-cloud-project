""" This module is used for providing High Level API for using encrypted 
    files, writing to them and reading to them. It uses tempfile for 
    convenience and subprocess + openssl to break the GIL. Most of all,
    it just demonstrates encrypting, and shouldn't be depended upon..."""

# Official
import asyncio
import tempfile
import os
import aiofiles
from typing import AsyncContextManager
from contextlib import asynccontextmanager
import subprocess
# Mine
from loop_config import LOOP

ENCRYPT_COMMAND = 'openssl enc -aes-256-cbc -pass pass:{} -in {} -out {} -pbkdf2'
DECRYPT_COMMAND = 'openssl enc -aes-256-cbc -pass pass:{} -d -in {} -out {} -pbkdf2'
PASSWORD = 'royadar'


class OpenSSLException(Exception):
    pass

class EncryptedFile:
    def __init__(self, path: str) -> None:
        self.path = path
    
    @asynccontextmanager
    async def get_read(self, ownership=False):
        try:
            async with aiofiles.tempfile.NamedTemporaryFile(delete=False) as file:
                await file.close()
                def do_async():
                    proc = subprocess.run(DECRYPT_COMMAND.format(PASSWORD, self.path, file.name), \
                                          capture_output=True, text=True)
                    return proc.returncode
                return_code = await asyncio.to_thread(do_async)
                if return_code != 0: raise OpenSSLException
            async with aiofiles.open(file.name, mode='rb') as f:
                yield f
        finally:
            if not ownership:
                os.remove(file.name)
                
    @asynccontextmanager
    async def get_write(self, ownership=False):
        try:
            async with aiofiles.tempfile.NamedTemporaryFile(mode='wb', delete=False) as file:
                yield file
                await file.close()
                
                def do_async():
                    proc = subprocess.run(ENCRYPT_COMMAND.format(PASSWORD, file.name, self.path), \
                                          capture_output=True, text=True)
                    return proc.returncode
                return_code = await asyncio.to_thread(do_async)
                if return_code != 0: raise OpenSSLException
        finally:
            if not ownership:
                os.remove(file.name)

async def main():
    async with EncryptedFile('.\Files\hello.aaa').get_write() as file:
        await file.write(b'hello client hello client'*20)

    async with EncryptedFile('.\Files\hello.aaa').get_read() as file:
        print(await file.read(1024))
    
if __name__ == '__main__':
    LOOP.run_until_complete(main())
