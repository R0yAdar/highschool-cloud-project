""" Wraps ConnectionSingleton TO mainatain simplicity and readbility."""

from ConnectionSingleton import ConnectionProxy
import RAP as RAP


class Requests:
    def __init__(self) -> None:
        self.singleton = ConnectionProxy()
    
    def Login(self, login_info: RAP.Login):
        return self.singleton.login(login_info)

    def SignupSendCode(self, email: str):
        return self.singleton.signup_send_code(RAP.SignupCode(email))

    def SignupVerifyCode(self, email: str, code: str):
        req = RAP.SignupCheckCode(email, code)
        return self.singleton.signup_verify_code(req)

    def SignupFull(self, email: str, password: str, code: str):
        req = RAP.SignupFull(email, code, password)
        return self.singleton.signup(req)
    
    def UploadFile(self, path: str, size: int, where: RAP.DirInfo):
        name = path.split('/')[-1]
        req = RAP.UploadFile(size, name, where)
        return self.singleton.upload_file(req, path)

    def DownloadFile(self, download_path: str, file: RAP.FileInfo, start=0, end=0):
        if start < end:
            return self.singleton.resume_download_file(download_path, RAP.FileDownload(file, start, end))
        return self.singleton.download_file(download_path, RAP.FileDownload(file))
    
    def CreateFolder(self, name: str, where: RAP.DirInfo) -> RAP.NodeResponse:
        return self.singleton.create_folder(RAP.CreateFolder(name, where))

    def ListDir(self, dir: RAP.DirInfo):
        return self.singleton.list_dir(dir)
    
    def MoveNode(self, node_id, dst_id):
        req = RAP.MoveNode(node_id, dst_id)
        return self.singleton.move_node(req)
    
    def CopyNode(self, node_id, dst_id):
        req = RAP.CopyNode(node_id, dst_id)
        return self.singleton.copy_node(req)
    
    def DeleteNode(self, node_id):
        req = RAP.DeleteNode(node_id)
        return self.singleton.delete_node(req) 

    def GetIcon(self, file: RAP.FileInfo) -> RAP.IcoResponse:
        req = RAP.GetIco(file)
        return self.singleton.get_icon(req)
    
    def ExtendedInfo(self, node_id: int) -> RAP.InfoResponse:
        return self.singleton.extended_info(node_id)

    def RenameNode(self, node_id: int, new_name: str) -> RAP.BasicResponse:
        return self.singleton.rename_node(node_id, new_name)

    def ShareNode(self, node_id: int, who: str) -> RAP.BasicResponse:
        return self.singleton.share_node(node_id, who)

    def UnshareNode(self, node_id: int, who: str) -> RAP.BasicResponse:
        return self.singleton.unshare_node(node_id, who)
    
    def GetFriendList(self) -> RAP.UserListResponse:
        return self.singleton.get_friend_list()
    
    def GetPendingList(self) -> RAP.UserListResponse:
        return self.singleton.get_pending_list()
    
    def SendFriendRequest(self, who: str) -> RAP.BasicResponse:
        return self.singleton.send_friend(who)
    
    def RejectFriendRequest(self, who: str) -> RAP.BasicResponse:
        return self.singleton.reject_friend(who)
    
    def AcceptFriendRequest(self, who: str) -> RAP.BasicResponse:
        return self.singleton.accept_friend(who)
    
    def RemoveFriend(self, who: str) -> RAP.BasicResponse:
        return self.singleton.remove_friend(who)

    def ZipFolder(self, which: int) -> RAP.BasicResponse:
        return self.singleton.zip_folder(which)

    def UnzipFolder(self, which: int) -> RAP.BasicResponse:
        return self.singleton.unzip_folder(which)

    def AskForStreamUrl(self, file: RAP.FileInfo) -> RAP.StreamResponse:
        return self.singleton.get_url(RAP.StreamRequest(file))

    def Pipeline(self, requests: RAP.PipelinedRequest, response_type):
        return self.singleton.pipeline(requests, response_type)

    def close(self):
        self.singleton.close()

def main():
    user = Requests()
    user.Login(RAP.Login('royadararmy@gmail.com', 'zaqWSX123#'))
    what = RAP.PipelinedRequest([RAP.Request(get_icon=RAP.GetIco(RAP.FileInfo(id=11))), RAP.Request(get_icon=RAP.GetIco(RAP.FileInfo(id=11)))])
    for i in user.Pipeline(what, RAP.IcoResponse):
        i: RAP.IcoResponse
        print(i)

    '''res: RAP.BasicResponse = user.SignupSendCode('royadararmy@gmail.com')
    if res.status == RAP.BasicResponseSTATUS.FAILED:
        print('FAILED')
        return
    code = input('Enter Code: ')
    res: RAP.BasicResponse = user.SignupFull('royadararmy@gmail.com', 'zaq123321', code)'''
    res: RAP.BasicResponse = user.Login(RAP.Login('royadararmy@gmail.com', 'zaq123321'))
    if not res[0]:
        print('FAILED')    
        return
    
    root = user.ListDir(RAP.DirInfo(id=0))
    myfiles = root.dirs[0]
    
    dir = user.ListDir(myfiles)
    print(dir.files[0])
    for n in user.DownloadFile("C:\\Users\\royad\\OneDrive\\Desktop\\random.proto", dir.files[0]):
        print(n)
    return
    user.CreateFolder('Another One', dir)
    dir = user.ListDir(dir).dirs[0]

    path = input('Enter File Path: ')
    res: RAP.BasicResponse = user.UploadFile(path, dir)
    if res.status == RAP.BasicResponseSTATUS.FAILED:
        print('FAILED')
    else:
        print('GOOD')
    print(user.ListDir(dir))

    return 
    path = input('Enter File Path: ')
    res: RAP.BasicResponse = user.UploadFile(path, root.dirs[0])
    if res.status == RAP.BasicResponseSTATUS.FAILED:
        print('FAILED')
    else:
        print('GOOD')
    

if __name__ == '__main__':
    main()

    #print(user.Login(RAP.Login("royadar@gmail.com", "zaq12321")))
    #print(sing.ListDir(RAP.DirInfo(display_name="", id=0)))

