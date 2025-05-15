""" Module for managing a user's state, requests to the Server.
    It is the simple API for interacting using the RAP protocol 
    with the server. This API is wrapped by custom HL Requests class."""


from contextlib import contextmanager
from hashlib import sha256
import Connections as Connections
import RAP as RAP
from Utilities import HashException, ServerFailure
from betterproto import decode_varint, encode_varint
import gzip
import tempfile

def send_protobuf(stream: Connections.SSLStream, message) -> None:
    encoded_message = message.SerializeToString()
    method = ""
    if len(encoded_message) > 4096:
        encoded_message = gzip.compress(encoded_message, 9)
        method = "gzip"

    encoded_message = RAP.MessageContainer(compression_method=method, payload=encoded_message).SerializeToString()
    stream.write(encode_varint(len(encoded_message)))
    stream.write(encoded_message)

def recv_protobuf(stream: Connections.SSLStream, message_type):
    buffer = stream.read(1)
    if not buffer:
        raise ConnectionError
    while True:
            try:
                size, newpos = decode_varint(buffer, 0, False)
                break
            except IndexError:
                buffer += stream.read(1)
                if not buffer:
                    raise ConnectionError
                if len(buffer) > 10:
                    raise ConnectionError # Arbitrary, message shouldn't be that big.
    
    data = buffer[newpos:] + stream.readexactly(size - len(buffer) + newpos)
    container = RAP.MessageContainer().parse(data)

    if container.compression_method == 'gzip':
        data = gzip.decompress(container.payload)
    else:
        data = container.payload
    message = message_type()
    message.parse(data)
    return message
    
class ConnectionProxy:
    def __init__(self) -> None:
        self.factory = Connections.SSLStreamFactory()
    
    @contextmanager
    def open_stream(self):
        stream = None
        try:
            stream = self.factory.get()
            yield stream
        finally:
            if stream:
                self.factory.ret(stream)
           
    def wrapped_request(self) -> RAP.RAP_Request:
        return RAP.RAP_Request(token=self.token)

    def signup(self, info: RAP.SignupFull):
        request = RAP.RAP_Request()
        request.request.signup_full = info

        with self.open_stream() as stream:
            send_protobuf(stream, request)
            response = recv_protobuf(stream, RAP.BasicResponse)
        if response.status == RAP.BasicResponseSTATUS.OK:
            valid, _  = self.login(RAP.Login(info.email, info.password))
        else:
            return response
        if valid:
            return RAP.BasicResponse(RAP.BasicResponseSTATUS.OK)
        return RAP.BasicResponse(RAP.BasicResponseSTATUS.FAILED)
    
    
    def signup_send_code(self, codereq: RAP.SignupCode):
        request = RAP.RAP_Request()
        request.request.signup_code_request = codereq
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            response: RAP.BasicResponse = recv_protobuf(stream, RAP.BasicResponse)
        return response


    def signup_verify_code(self, req: RAP.SignupCheckCode):
        request = RAP.RAP_Request()
        request.request.signup_check_code = req
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            response: RAP.BasicResponse = recv_protobuf(stream, RAP.BasicResponse)
        return response
    
    def login(self, login: RAP.Login) -> tuple:
        # Should be updated to use the better pattern.
        request = RAP.RAP_Request()
        request.request.login_request = login
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            response: RAP.LoginResponse = recv_protobuf(stream, RAP.LoginResponse)        
        
        if response.status == RAP.LoginResponseSTATUS.FAILED:
            return (False, "Failed")
        self.token = response.token
        return (True, "OK")
        

    def list_dir(self, dir: RAP.DirInfo) -> RAP.ListDir:
        request = self.wrapped_request()
        request.request.list_dir_request = dir

        with self.open_stream() as stream:
            send_protobuf(stream, request)
            contents: RAP.ListDir = recv_protobuf(stream, RAP.ListDir)
            return contents

    def upload_file(self, upload_file: RAP.UploadFile, file_path: str):
        BUFFER = 1024 * 10
        request = self.wrapped_request()
        h = sha256()
        with open(file_path,'rb') as f: 
            while chunk := f.read(BUFFER*h.block_size): 
                h.update(chunk)
        upload_file.sha256 = h.hexdigest()
        request.request.file_upload = upload_file
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            size = upload_file.size
            with open(file_path, mode='rb') as f:
                while size:
                    data = f.read(BUFFER)
                    n = len(data)
                    stream.write(data)
                    size -= n
                    yield n

            response: RAP.NodeResponse = recv_protobuf(stream, RAP.NodeResponse)
        yield response

    def download_file(self, download_path: str, req: RAP.FileDownload):
        BUFFER = 1024 * 10
        request = self.wrapped_request()
        request.request.download_file = req

        with self.open_stream() as stream:
            send_protobuf(stream, request)

            res: RAP.BasicResponse = recv_protobuf(stream, RAP.BasicResponse)
            if res.status == RAP.BasicResponseSTATUS.OK:
                size = req.file.size
                with open(download_path, mode='wb') as f:
                    file_hash = sha256()
                    while size:
                        data = stream.read(BUFFER)
                        n = f.write(data)
                        file_hash.update(data)
                        if not n: 
                            raise ConnectionError
                        size -= n
                        yield n

                if req.file.sha256 and file_hash.hexdigest() != req.file.sha256:
                    raise HashException
            else:
                raise ServerFailure
        yield None
    
    def download_into(self, file: tempfile._TemporaryFileWrapper, req: RAP.FileDownload):
        BUFFER = 1024 * 10
        request = self.wrapped_request()
        request.request.download_file = req
        with self.open_stream() as stream:
            send_protobuf(stream, request)

            res: RAP.BasicResponse = recv_protobuf(stream, RAP.BasicResponse)
            if res.status == RAP.BasicResponseSTATUS.OK:
                size = req.file.size
                while size:
                    n = file.write(stream.read(BUFFER))
                    size -= n
                    if not n: 
                        raise ConnectionError
        
    def resume_download_file(self, download_path: str, req: RAP.FileDownload):
        BUFFER = 1024 * 10
        request = self.wrapped_request()
        request.request.download_file = req
        
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            size = req.end - req.start
            res: RAP.BasicResponse = recv_protobuf(stream, RAP.BasicResponse)
            if res.status == RAP.BasicResponseSTATUS.OK:
                h = sha256()
                with open(download_path, mode='rb') as f:
                    while req.start:
                        data = f.read(BUFFER)
                        h.update(data)
                        req.start -= len(data)
                        
                with open(download_path, mode='ab') as f:
                    f.seek(req.start)
                    while size > 0:
                        data = stream.read(BUFFER)
                        n = f.write(data)
                        h.update(data)
                        size -= n
                        if not n: 
                            raise ConnectionError
                        yield n

            if req.file.sha256 and h.hexdigest() != req.file.sha256:
                raise HashException
        yield None
    
    def create_folder(self, req: RAP.CreateFolder):
        request = self.wrapped_request()
        request.request.create_folder = req

        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.NodeResponse)

    def move_node(self, req: RAP.MoveNode):
        request = self.wrapped_request()
        request.request.move_node = req

        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)

    def copy_node(self, req: RAP.CopyNode):
        request = self.wrapped_request()
        request.request.copy_node = req
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
    
    def delete_node(self, req: RAP.DeleteNode):
        request = self.wrapped_request()
        request.request.delete_node = req
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
    
    def get_icon(self, req: RAP.GetIco) -> RAP.IcoResponse:
        request = self.wrapped_request()
        request.request.get_icon = req
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.IcoResponse)

    def get_url(self, req: RAP.StreamRequest) -> RAP.StreamResponse:
        request = self.wrapped_request()
        request.request.get_stream = req
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.StreamResponse)

    def extended_info(self, node_id: int) -> RAP.InfoResponse:
        request = self.wrapped_request()
        request.request.extended_info = RAP.Node(node_id)
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.InfoResponse)

    def rename_node(self, node_id: int, new_name: str) -> RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.rename_node = RAP.RenameNode(RAP.Node(node_id), new_name)
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse) 

    def share_node(self, node_id: int, with_email: str) -> RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.share_node = RAP.NodeUser(email=with_email, node=RAP.Node(node_id))
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
    
    def unshare_node(self, node_id: int, with_email: str) -> RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.unshare_node = RAP.NodeUser(email=with_email, node=RAP.Node(node_id))
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
    
    def get_friend_list(self) -> RAP.UserListResponse:
        request = self.wrapped_request()
        request.request.friend_list = True
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.UserListResponse)
    
    def get_pending_list(self) -> RAP.UserListResponse:
        request = self.wrapped_request()
        request.request.pending_friends = True
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.UserListResponse)
        
    def reject_friend(self, who: str) -> RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.reject_friend = RAP.User(who)
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
    
    def accept_friend(self, who: str) -> RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.accept_friend = RAP.User(who)
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
    
    def remove_friend(self, who: str) -> RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.remove_friend = RAP.User(who)
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
    
    def send_friend(self, who: str) ->RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.send_friend = RAP.User(who)
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
        
    def zip_folder(self, which: int) ->RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.zip_request = RAP.Node(which)
        with self.open_stream() as stream:
            stream.socket.settimeout(60*60) #! Theoretically should be handled in a notifications persistent connection...
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)
        
    def unzip_folder(self, which: int) ->RAP.BasicResponse:
        request = self.wrapped_request()
        request.request.unzip_request = RAP.Node(which)
        with self.open_stream() as stream:
            stream.socket.settimeout(60*60) #!
            send_protobuf(stream, request)
            return recv_protobuf(stream, RAP.BasicResponse)

    def pipeline(self, req: RAP.PipelinedRequest, response_type):
        request = self.wrapped_request()
        request.request.pipelined_request = req
        with self.open_stream() as stream:
            send_protobuf(stream, request)
            amount = len(req.requests)
            for i in range(amount):
                yield recv_protobuf(stream, response_type)

    def close(self):
        self.factory.clear()
