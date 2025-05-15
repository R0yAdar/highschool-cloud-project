""" This is the code for the main server, it handles most of the App's operations above
    the custom RAP protocol. It doesn't handle the mp4 HTTPS streaming (for that there's
    the streaming_server).
"""

# Official 
from asyncio import StreamReader, StreamWriter
import asyncio
import ssl
from typing import Dict, List, Any
from types import AsyncGeneratorType
import gzip
from zipfile import ZipFile, BadZipFile
import hashlib
import datetime
import os
# 3rd Party
from betterproto import Message, which_one_of, encode_varint, decode_varint
from print_color import print # temporary (for nice colored prints)
# Mine
import RAP
import tools as tools
import peewee_db as pwDB
from peewee_db import User
from loop_config import LOOP
from file_encryption import EncryptedFile
import manager


PORT = '12345'
FILES_PATH = '.\\Files\\'
STREAMING_SERVER = 'https://127.0.0.1:443'
USERS: Dict[str, Any] = {}
ENCRYPT_COMMAND = 'openssl enc -aes-256-cbc -pass pass:{} -in {} -out {} -pbkdf2'
DECRYPT_COMMAND = 'openssl enc -aes-256-cbc -pass pass:{} -d -in {} -out {} -pbkdf2'
PASSWORD = 'royadar'

app = manager.Manager()

async def send_protobuf(writer: StreamWriter, message: Message):
    """ This function sends a serialized protobuf message on a stream, it encapsulates it as a payload
        of a container protobuf, and then sends it prefixed with it's size as a varint (bytes)"""
    encoded_message = message.SerializeToString()
    method = ""
    if len(encoded_message) > 4096:
        encoded_message = gzip.compress(encoded_message, 9)
        method = "gzip"

    encoded_message = RAP.MessageContainer(compression_method=method, payload=encoded_message).SerializeToString()
    writer.write(encode_varint(len(encoded_message)))
    writer.write(encoded_message)
    await writer.drain()

async def recv_protobuf(reader: StreamReader) -> RAP.RAP_Request:
    """ This function is used to read a protobuf Request of the custom protocol from an existing
        data stream, it expecets the message to be prefixed with its size. It first reads the size
        and then proceeds to read the entire message, parse it and return it to """
    buffer = await reader.read(1)
    if not buffer:
        raise RuntimeError("Connection Error")
    while True:
        try:
            size, newpos = decode_varint(buffer, 0, False)
            break
        except IndexError:
            buffer += await reader.read(1)
            if not buffer:
                raise RuntimeError("Connection Error")
            if len(buffer) > 10:
                raise RuntimeError("Connection Error") # Arbitrary, message shouldn't be that big.
    data = buffer[newpos:] + await reader.readexactly(size - len(buffer) + newpos)

    container = RAP.MessageContainer().parse(data)

    if container.compression_method == 'gzip':
        data = gzip.decompress(container.payload)
    else:
        data = container.payload
    
    message = RAP.RAP_Request().parse(data)
    return message

def get_availaible_path() -> str:
    """ This function is used to get an availaible path for storing a file in the filesystem
        currently it bases the name on the file's upload time..."""
    path = FILES_PATH + str(datetime.datetime.now()).replace(':', '_').replace(' ', '')
    if os.path.exists(path):
        return get_availaible_path()
    return path

@app.add_route('pipelined_request', requires_auth=True, requires_reader=True)
async def handling_multiple_requests(requests: RAP.PipelinedRequest, user: User, reader: StreamReader):
    """ This is an endpoint for handling pipelined requests which are a bunch of requests ququed
        one after the other. Responses return at the same order and are subject to HOL blocking"""
    for thing in requests.requests:
        name, request = which_one_of(thing, "requests")
        service, requires_auth, requires_reader = app.serve(name)
        if requires_auth:
            if requires_reader:
                yield await service(request, user, reader)
            else:
                yield await service(request, user)
        else:
            if requires_reader:
                yield await service(request, reader)
            else:
                yield await service(request)

def __zip_full_namelist(namelist: List[str]) -> List[str]:
    """ This is basically a tool/helper function that fixes 
       this bug: https://bugs.python.org/issue34738. 
       It should be moved to tools.py sometime in the future."""
    dir_list = set()
    for thing in namelist:
        prefix = ""
        splitted = thing.split('/')
        if splitted[-1] == "":
            splitted.pop()
        if thing[-1] == '/':
            for part in splitted:
                prefix += part + '/'
                dir_list.add(prefix)
        else:
            for part in splitted[0: -1]:
                prefix += part + '/'
                dir_list.add(prefix)
    return list(dir_list)

@app.add_route('unzip_request', requires_auth=True)
async def handle_unzipping(request: RAP.Node, user: User) -> RAP.BasicResponse:
    """ This is a complicated function-endpoint that handles unzipping an uploaded 
        zip file."""
    node = await pwDB.get_filesystemnode_by_id(user, request.id)
    if not node: return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    if user == await pwDB.get_owner(user, node):
        file = await pwDB.async_manager._get_foreign_key_target(node, 'file')
        if not file: return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
        parent = await pwDB.async_manager._get_foreign_key_target(node, 'parent')
        if not parent: return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
        ancestor = await pwDB.add_folder(user, parent, node.name)
        lookup_table: Dict[str, pwDB.FileSystemNode] = {}
        if not ancestor: return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
        lookup_table['/'] = ancestor
        try:
            async with EncryptedFile(file.real_path).get_read() as _file:
                await _file.close()
                with ZipFile(_file.name) as zip_file:
                    dir_names = sorted(__zip_full_namelist(zip_file.namelist()))
                    for dir_name in dir_names:
                        before = '/'.join(dir_name.split('/')[0: -2]) + '/'
                        current = await pwDB.add_folder(user, lookup_table[before], dir_name.split('/')[-2])
                        if not current: return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
                        lookup_table[dir_name] = current
                    for file_path in zip_file.namelist():
                        if file_path[-1] == '/':
                            continue
                        else:
                            parts = file_path.split('/')
                            where = lookup_table["/".join(parts[0: -1])+'/']
                            info = zip_file.NameToInfo[file_path]
                            path = get_availaible_path()
                            async with EncryptedFile(path).get_write() as __file:
                                await __file.close()
                                info.filename = __file.name.split('\\')[-1] # In order to extract without structure:
                                                                            # https://stackoverflow.com/questions/4917284/extract-files-from-zip-without-keeping-the-structure-using-python-zipfile
                                await asyncio.to_thread(zip_file.extract, info, '/'.join(__file.name.split('\\')[0:-1]))

                                h = hashlib.sha256()
                                with open(__file.name,'rb') as f: 
                                    while chunk := f.read(128*h.block_size): 
                                        h.update(chunk)
                                await pwDB.add_file(user, where, parts[-1], await pwDB.file_association(path, user, os.path.getsize(__file.name), h.hexdigest()))
            return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
        except BadZipFile:
            pass
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)  


@app.add_route('zip_request', requires_auth=True)
async def handle_zipping(request: RAP.Node, user: User) -> RAP.BasicResponse:
    """ This endpoint is used to zip an existing folder from the user's filesystem."""
    node = await pwDB.get_filesystemnode_by_id(user, request.id)
    if not node: return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    if user == await pwDB.get_owner(user, node):
        path = get_availaible_path()
        async with EncryptedFile(path).get_write() as file:
            await file.close()
            with ZipFile(file.name, 'w') as zip_file:
                things = await pwDB.get_paths_for_zip(node)
                for key in things:
                    where = things[key]
                    async with EncryptedFile(where).get_read() as f:
                        await f.close()
                        await asyncio.to_thread(zip_file.write, f.name, key)
        # Calculate Hash: 
        h = hashlib.sha256()
        async with EncryptedFile(path).get_read() as f: #
            while chunk := await f.read(128*h.block_size): 
                h.update(chunk)

            await pwDB.add_file(user, await pwDB.async_manager._get_foreign_key_target(node, 'parent') \
                                , node.name + ".zip", await pwDB.file_association(path, user, os.path.getsize(f.name), h.hexdigest()))
            return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)  


@app.add_route('unshare_node', requires_auth=True)
async def handle_unsharing(request: RAP.NodeUser, user: User) -> RAP.BasicResponse:
    """ Endpoint for unsharing a node to a user."""
    who = await pwDB.get_user_from_email(request.email)
    what = await pwDB.get_filesystemnode_by_id(user, request.node.id)
    if (not who) or (not what):
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    status = await pwDB.remove_share(user, who, what)
    if not status:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)

@app.add_route('share_node', requires_auth=True)
async def handle_sharing(request: RAP.NodeUser, user: User) -> RAP.BasicResponse:
    """ Endpoint for sharing a node to a user."""
    who = await pwDB.get_user_from_email(request.email)
    what = await pwDB.get_filesystemnode_by_id(user, request.node.id)
    if (not who) or (not what):
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    status = await pwDB.share_node(user, who, what)
    if not status:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)

@app.add_route('remove_friend', requires_auth=True)
async def handle_removing(request: RAP.User, user: User) -> RAP.BasicResponse:
    """ Endpoint for removing an existing friend."""
    status = await pwDB.remove_friend(user, request.email)
    if not status:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)

@app.add_route('reject_friend', requires_auth=True)
async def handle_rejecting(request: RAP.User, user: User) -> RAP.BasicResponse:
    """ Endpoint for rejecting a friend request that was sent to you."""
    status = await pwDB.reject_friend(user, request.email)
    if not status:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)

@app.add_route('send_friend', requires_auth=True)
async def handle_sending(request: RAP.User, user: User) -> RAP.BasicResponse:
    """ Endpoint for sending a friend request to another user."""
    status = await pwDB.send_friend(user, request.email)
    if not status:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)

@app.add_route('accept_friend', requires_auth=True)
async def handle_accepting(request: RAP.User, user: User) -> RAP.BasicResponse:
    """ Endpoint for accepting a friend request that was sent to you."""
    status = await pwDB.accept_friend(user, request.email)
    if not status:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)

@app.add_route('pending_friends', requires_auth=True)
async def handle_pending_list(request, user: User) -> RAP.UserListResponse:
    """ Endpoint for getting the list of the pending friend requests that 
        were sent to you."""
    friend_list = await pwDB.get_pending(user)
    return RAP.UserListResponse(RAP.UserList(friend_list), RAP.BasicResponse(RAP.BasicResponseSTATUS.OK))

@app.add_route('friend_list', requires_auth=True)
async def handle_friend_list(request, user: User) -> RAP.UserListResponse:
    """ Endpoint for getting your friend list."""
    friend_list = await pwDB.get_friends(user)
    return RAP.UserListResponse(RAP.UserList(friend_list), RAP.BasicResponse(RAP.BasicResponseSTATUS.OK))

@app.add_route('rename_node', requires_auth=True)
async def handle_renaming(request: RAP.RenameNode, user: User) -> RAP.BasicResponse:
    """ Endpoint for renaming a node in a user's filesystem (file/folder)."""
    if not (node := await pwDB.get_filesystemnode_by_id(user, request.node.id)):
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    if (await pwDB.rename_node(user, node, request.new_name)):
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)

@app.add_route('extended_info', requires_auth=True)
async def handle_extended_info(request: RAP.Node, user: User) -> RAP.InfoResponse:
    """ Endpoint for getting the extended information on a node in the filesystem,
        it includes fields like: Size, Upload Date, Shared With List, etc."""
    if info := await pwDB.get_extended_info_by_id(user, request.id):
        return RAP.InfoResponse(info, RAP.BasicResponse(RAP.BasicResponseSTATUS.OK))
    return RAP.InfoResponse(response=RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED))


@app.add_route('file_upload', requires_auth=True, requires_reader=True)
async def handling_upload(request: RAP.UploadFile, user: User, payload_iterator: StreamReader) -> RAP.NodeResponse:
    """ This endpoint is used for uploading files to a user's filesystem or to a shared 
        folder."""
    BUFFER = 1024*10 # Completely arbitrary.
    file_size = request.size
    name = request.display_name

    file_node = await pwDB.get_filesystemnode_by_id(user, request.place.id)
    if not file_node:
        return RAP.NodeResponse(response=RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED))
    else:
        path = get_availaible_path()
        hash = hashlib.sha256()
        async with EncryptedFile(path).get_write() as f: #
            while file_size:
                data = await payload_iterator.read(BUFFER)
                n = await f.write(data)
                hash.update(data)
                if n == 0:
                    # Connection Got Cut
                    file = await pwDB.file_association(path, user, request.size, hash.hexdigest())
                    if not file:
                        return RAP.NodeResponse(response=RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED))
                    await pwDB.add_file(user, file_node, name+'.PARTIAL', file)
                    return RAP.NodeResponse(response=RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED))
                file_size -= n
            hash_digest = hash.hexdigest()
            if  hash_digest != request.sha256:
                name = name + '.HASH'

            file = await pwDB.file_association(path, user, request.size, hash_digest)
            if file:
                node = await pwDB.add_file(user, file_node, name, file)
            else:
                return RAP.NodeResponse(response=RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED))
            if node:
                return RAP.NodeResponse(node.get_id(), RAP.BasicResponse(RAP.BasicResponseSTATUS.OK))
            else:
                return RAP.NodeResponse(response=RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED))


@app.add_route('download_file', requires_auth=True)
async def handling_download(request: RAP.FileDownload, user: User):
    """ Endpoint for downloading a file that was shared with a user, 
        or belongs to him (in his filesystem/trash)."""
    BUFFER = 1024 * 10 # Completely arbitrary.
    file_node = await pwDB.get_filesystemnode_by_id(user, request.file.id)
    if not file_node:
        yield RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    else:
        path: str = (await pwDB.async_manager._get_foreign_key_target(file_node, 'file')).real_path
        if not os.path.exists(path):
            yield RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
        yield RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
    
    if request.start != request.end:
        async with EncryptedFile(path).get_read() as f:
            await f.seek(request.start)
            to_read = request.end - request.start
            while to_read > 0:
                n = await f.read(BUFFER)
                if not n: return
                yield n
                to_read -= len(n)
    else:          
        async with EncryptedFile(path).get_read() as f:
            while len(data := await f.read(BUFFER)) > 0:
                yield data
    return

@app.add_route('signup_code_request', requires_auth=False)
async def handle_code_sending(request: RAP.SignupCode) -> RAP.BasicResponse:
    """ Endpoint for getting a signup code that is essential for creating
        a new account."""
    await tools.send_auth_mail(request.my_email)
    return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)

@app.add_route('signup_check_code', requires_auth=False)
async def handle_code_check(request: RAP.SignupCheckCode) -> RAP.BasicResponse:
    """ Endpoint for checking that the code is good (exists in order to be 
    able to advance in the GUI to password choosing page)."""
    if (await tools.check_auth_code(request.email, request.code)):
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
    else:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)

@app.add_route('signup_full', requires_auth=False)
async def handle_full_signup(request: RAP.SignupFull) -> RAP.BasicResponse:
    """ Endpoint for completing the signup process."""
    if not await tools.check_auth_code(request.email, request.verf_code):
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    user = await pwDB.create_user(request.email, request.password)
    if user:
        await pwDB.create_filesystem_root(user) 
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
    else:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)

@app.add_route('create_folder')
async def handle_folder_creation(request: RAP.CreateFolder, user: User) -> RAP.NodeResponse:
    """ Endpoint for creating a folder in your filesystem."""
    where = await pwDB.get_filesystemnode_by_id(user, request.place.id)
    if not where:
        return RAP.NodeResponse(response=RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED))
    node = await pwDB.add_folder(user, where, request.display_name)
    if not node:
        return RAP.NodeResponse(response=RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED))
    
    return RAP.NodeResponse(node.get_id(), RAP.BasicResponse(RAP.BasicResponseSTATUS.OK))


@app.add_route('move_node')
async def handle_node_moving(request: RAP.MoveNode, user: User) -> RAP.BasicResponse:
    """ Endpoint for moving a node in your filesystem."""
    src = await pwDB.get_filesystemnode_by_id(user, request.src_id)
    if request.dst_id == 0:
        dst = await pwDB.get_filesystem_root(user)
    else:
        dst = await pwDB.get_filesystemnode_by_id(user, request.dst_id) # type: ignore

    if not src or not dst:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    result = await pwDB.move_node(user, src, dst)
    if result:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
    else:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)


@app.add_route('delete_node')
async def handle_node_deleting(request: RAP.DeleteNode, user: User) -> RAP.BasicResponse:
    """ Endpoint for deleting a node from the filesystem or from trash, 
        files that are deleted in trash are irecoverable."""
    root = await pwDB.get_filesystemnode_by_id(user, request.node_id)
    if not root:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    
    result = await pwDB.delete_node(user, root)
    if result:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
    else:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)

@app.add_route('copy_node')
async def handle_copying(request: RAP.CopyNode, user: User) -> RAP.BasicResponse:
    """ Endpoint for copying a node or a branch of nodes from one place to another."""
    src = await pwDB.get_filesystemnode_by_id(user, request.src_id)
    dst = await pwDB.get_filesystemnode_by_id(user, request.dst_id)
    if not src or not dst:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    result = await pwDB.copy_branch(user, src, dst)
    if result:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
    else:
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)


@app.add_route('get_icon')
async def get_icon(request: RAP.GetIco, user: User) -> RAP.IcoResponse:
    """ Endpoint for getting the icon of a node (basically image preview)."""
    if not user:
        return RAP.IcoResponse(response=RAP.BasicResponse(status=RAP.BasicResponseSTATUS.FAILED))
    node = await pwDB.get_filesystemnode_by_id(user, request.info.id)

    if not node:
        return RAP.IcoResponse(response=RAP.BasicResponse(status=RAP.BasicResponseSTATUS.FAILED))
    icon = await tools.get_ico((await pwDB.async_manager._get_foreign_key_target(node, 'file')).real_path)
    return RAP.IcoResponse(image=icon, response=RAP.BasicResponse(status=RAP.BasicResponseSTATUS.OK))


@app.add_route('get_stream')
async def get_stream(request: RAP.StreamRequest, user: User) -> RAP.StreamResponse:
    """ Endpoint for getting the stream URL (streaming of a mp4 file over HTTPS 
        with 206 responses, with the streaming_server)."""
    if not user:
            return RAP.StreamResponse(url=f'{STREAMING_SERVER}/watch/?v=', \
                                                        response=RAP.BasicResponse(status=RAP.BasicResponseSTATUS.OK)) # default
    node = await pwDB.get_filesystemnode_by_id(user, request.file.id)
    if not node:
        return RAP.StreamResponse(url=f'{STREAMING_SERVER}/watch/?v=', \
                                                        response=RAP.BasicResponse(status=RAP.BasicResponseSTATUS.OK)) # default
    
    if stream := await pwDB.create_streamable(user, await pwDB.async_manager._get_foreign_key_target(node, 'file')):
        return RAP.StreamResponse(url=f'{STREAMING_SERVER}/watch/?v={stream.url_token}', \
                                                        response=RAP.BasicResponse(status=RAP.BasicResponseSTATUS.OK))
    
    if stream := await pwDB.get_streamable(user, await pwDB.async_manager._get_foreign_key_target(node, 'file')):
        return RAP.StreamResponse(url=f'{STREAMING_SERVER}/watch/?v={stream.url_token}', \
                                                        response=RAP.BasicResponse(status=RAP.BasicResponseSTATUS.OK))
    
    return RAP.StreamResponse(response=RAP.BasicResponse(status=RAP.BasicResponseSTATUS.FAILED))


@app.add_route('list_dir_request')
async def handle_dir_listing(request: RAP.DirInfo, user: User) -> RAP.ListDir:      
    """ Endpoint for getting a list of the files and directories contained in
        a specified directory."""
    if request.id == 0:
        node = await pwDB.get_filesystem_root(user)
        return RAP.ListDir(dirs=[RAP.DirInfo('MyFiles', id=node.get_id())])
    
    if request.id == 1:
        data = await pwDB.get_shared_roots(user)
    elif request.id == 2:
        data = await pwDB.get_trash(user)
    elif root := await pwDB.get_filesystemnode_by_id(user, request.id):
        data = await pwDB.list_files(user, root)
    else:
        return RAP.ListDir()
    
    dirs: List[RAP.DirInfo] = []
    files: List[RAP.FileInfo] = [] 
    for node in data:
        if await node.is_folder():
            dirs.append(RAP.DirInfo(display_name=node.name, id=node.get_id()))

        else:
            file = (await pwDB.async_manager._get_foreign_key_target(node, 'file'))
            s = file.size
            hash = file.sha256
            files.append(RAP.FileInfo(display_name=node.name, id=node.get_id(), size=s, sha256=hash))
    return RAP.ListDir(dirs=dirs, files=files)

@app.add_route('login_request', requires_auth=False)
async def handle_login(request: RAP.Login) -> RAP.LoginResponse:
    """ Endpoint for logging in the system (getting a session token...)"""
    token = await pwDB.auth_user(request.email, request.password)
    if token:
        return RAP.LoginResponse(RAP.LoginResponseSTATUS.OK, RAP.Token(token))
    else:
        return RAP.LoginResponse(RAP.LoginResponseSTATUS.FAILED)

async def handler(reader: StreamReader, writer: StreamWriter) -> None:
    """ The main function that handles new connections to the server.
        It classifies the request, calls the handling function, logs 
        the user's connection + IP and more..."""
    peer_ip, port = writer.get_extra_info('peername')
    if not peer_ip in USERS or USERS[peer_ip]["when"] - datetime.datetime.utcnow().timestamp() > 60:
        USERS[peer_ip] = {"count": 0, "when": datetime.datetime.utcnow().timestamp()}
    USERS[peer_ip]["count"] += 1
    await asyncio.sleep(USERS[peer_ip]["count"]/100000.0) # Just to emphasize the need for quota system...
    
    try:
        message: RAP.RAP_Request = await asyncio.wait_for(recv_protobuf(reader), timeout=5.0)
    except ConnectionError:
        return print('Connection Got Cut During Reciving', tag='failure', tag_color='red')
    except asyncio.exceptions.TimeoutError:
        return print('Hit Timeout During Reciving', tag='failure', tag_color='red')


    name, request = which_one_of(message.request, "requests")
    try:    
        service, requires_auth, requires_reader = app.serve(name)
    except ValueError as e:
        return print(e, tag='failure', tag_color='red')

    
    if requires_auth:
        user = await pwDB.identify_user(message.token)
        if not user:
            return
        if requires_reader:
            response = service(request, user, reader)
        else:
            response = service(request, user)
    else:
        if requires_reader:
            response = service(request, reader)
        else:
            response = service(request)

    try:
        if isinstance(response, AsyncGeneratorType):
            try:
                async for value in response:
                    if issubclass(type(value), Message):
                        await send_protobuf(writer, value)
                    elif isinstance(value, bytes):
                        if len(value) > 0:
                            writer.write(value)
            except StopAsyncIteration:
                pass
        else:
            await send_protobuf(writer, await response)
    except ConnectionError:
        return print('Connection Got Cut During Sending', tag='failure', tag_color='red')
    except ValueError as e:
        return print(e, tag='failure', tag_color='red')
    except RuntimeError as e:
        return print(e, tag='failure', tag_color='red')
    try:
        await writer.drain()
    except ConnectionError:
        pass
    
    print(f'Handled {name}', tag='success', tag_color='green')
    writer.close()
    try:
        await writer.wait_closed()
    except (ConnectionResetError, ConnectionAbortedError, TimeoutError):
        pass

async def main():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('rap.crt', 'rap.key')

    server = await asyncio.start_server(
        handler, '127.0.0.1', PORT, ssl=context)

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f'Serving on {addrs}')

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    LOOP.run_until_complete(main())
