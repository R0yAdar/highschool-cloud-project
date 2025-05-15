""" The main module for managing the (main) postgres database, used in order to make queries, etc."""
# 3rd party:
from peewee import SqliteDatabase, CharField, Model, TextField, ForeignKeyField, IntegerField, DateTimeField, IntegrityError, DoesNotExist, TimestampField, BackrefAccessor
import peewee_async

# Official
import asyncio
from typing import List, Dict, Optional, Type, Set
from datetime import datetime
import hashlib
import secrets

# Mine
import RAP
from loop_config import LOOP
from tools import slugify

DB = peewee_async.PostgresqlDatabase('postgres', user='postgres', password='RoyAdar',
                        host='127.0.0.1', port=5432) # Creating Postgres Database Setting

class AsyncManager(peewee_async.Manager):
    """ This manager is used to easily interact with peewee in async, and is inspired
        from this GitHub Issue: https://github.com/05bit/peewee-async/issues/15. """
    async def get_related(self, instance, related_name, single_backref=False):
        """
        return related instance for foreign key relationship
        return query for backref or return related instance if single_backref is True
        """
        model_cls = type(instance)
        related_field = getattr(model_cls, related_name)

        if isinstance(related_field, BackrefAccessor):
            return await self._get_backrefs(instance, related_name, single_backref)
        else:
            return await self._get_foreign_key_target(instance, related_name)

    async def _get_foreign_key_target(self, instance, field_name):
        foreign_key_value = getattr(instance, field_name + "_id")
        if not foreign_key_value:
            return None
        model_cls = type(instance)
        foreign_key_field = getattr(model_cls, field_name)
        target_cls = foreign_key_field.rel_model
        target_field = foreign_key_field.rel_field
        #print(f"<<{target_cls}.... {target_field}.... {foreign_key_value}>>")
        return await self.get(target_cls, target_field == foreign_key_value)

    async def _get_backrefs(self, instance, related_name, single_backref=False):
        query = getattr(instance, related_name)
        instances = await self.execute(query)

        if single_backref:
            for instance in instances:
                return instance
            raise query.model_class.DoesNotExist
        else:
            return instances
        
    async def get_or_none(self, model_: Type[Model], defaults=None, **kwargs):
        try:
            return (await self.get(model_, **kwargs))
        except model_.DoesNotExist:
            return None
# Async Settings:

async_manager = AsyncManager(DB, loop=LOOP)
async_manager.database.allow_sync = False

# Models:
class BaseModel(Model):
    class Meta:
        database = DB

class User(BaseModel):
    email = CharField(unique=True)
    password_hash = CharField()
    password_salt = CharField()
    secret_token = TextField(unique=True)

    def __repr__(self) -> str:
        return f"<email='{self.email}', hash='{self.password_hash}', salt='{self.password_salt}'>"

class File(BaseModel):
    real_path = CharField()
    owner = ForeignKeyField(User, backref='files', on_delete='CASCADE')
    size = IntegerField()
    upload_time = IntegerField(default=datetime.timestamp(datetime.utcnow()))
    sha256 = CharField(null=True)

    def __repr__(self) -> str:
        return f"<path={self.real_path}; owner={self.owner.email}>"

class FileSystemNode(BaseModel):
    name = CharField()
    parent = ForeignKeyField('self', backref='children', null=True)
    owner = ForeignKeyField(User, backref='nodes', on_delete='CASCADE')
    file = ForeignKeyField(File, backref='used_at', null=True, on_delete='CASCADE')
    expire_date = DateTimeField(null=True)

    async def is_folder(self) -> bool:
        if not await async_manager._get_foreign_key_target(self, 'file'):
            return True
        return False      

    def __repr__(self) -> str:
        return f"<name={self.name}; owner={self.owner.email}; expire_date={self.expire_date}>"

class Friends(BaseModel):
    user1 = ForeignKeyField(User, backref='friends', on_delete='CASCADE')
    user2 = ForeignKeyField(User, backref='friends', on_delete='CASCADE')

    def __repr__(self) -> str:
        return f"<user1={self.user1.email}\ user2={self.user2.email}>"

class FriendRequest(BaseModel):
    sender = ForeignKeyField(User, backref='ongoing_friend_requests', on_delete='CASCADE')
    reciever = ForeignKeyField(User, backref='friend_requests', on_delete='CASCADE')
    timestamp = TimestampField(utc=True)

class SharedNode(BaseModel):
    shared_with = ForeignKeyField(User, backref='shared_nodes', on_delete='CASCADE')
    node = ForeignKeyField(FileSystemNode, backref='shared_with', on_delete='CASCADE')

class Streamable(BaseModel):
    file = ForeignKeyField(File, backref='stream', unique=True, on_delete='CASCADE')
    url_token = CharField(unique=True)

# Functions for intializing the database:

def drop_tables():
    DB.drop_tables([User, FileSystemNode, File, Friends, FriendRequest, SharedNode, Streamable])

def startup(first_time=False):
    DB.create_tables([User, FileSystemNode, File, Friends, FriendRequest, SharedNode, Streamable])
    if first_time:
        user = User.create(email='royadar@gmail.com', password_hash='', password_salt='', secret_token=secrets.token_hex(32))
        # IMPORTANT To Reserve Indexes 0, 1, 2 For My Files, Shared Files and Trash IMPORTANT :
        FileSystemNode.create(name='SharedFiles', owner=user) 
        FileSystemNode.create(name='Trash', owner=user)

""" Functions for interacting with the database (almost all of them 
    completely describe themselves without external notes): """

async def create_streamable(user: User, file: File) -> Optional[Streamable]:
    if await async_manager._get_foreign_key_target(file, 'owner') != user: return None
    try:
        return await async_manager.create(Streamable, file=file, url_token=secrets.token_urlsafe(64))
    except IntegrityError:
        return None

async def get_streamable(user: User, file: File) -> Optional[Streamable]:
    if await async_manager._get_foreign_key_target(file, 'owner') != user: return None
    try:
        return await async_manager.get(Streamable, file=file)
    except DoesNotExist:
        return None

async def get_stream_by_token(token: str) -> Optional[Streamable]:
    try:
        return await async_manager.get(Streamable, url_token=token)
    except DoesNotExist: return None

async def create_user(email: str, password: str)-> Optional[User]:
    if len(password) > 255 or len(email) > 255:
        return None
    try:
        salt = secrets.token_hex(16)
        hashed_password = hashlib.scrypt(password=password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        # Settings from here: https://cryptobook.nakov.com/mac-and-key-derivation/scrypt.
        secret_token = secrets.token_hex(32)
        return await async_manager.create(User, email=email, password_hash=hashed_password, \
                                    password_salt=salt, secret_token=secret_token)
    except IntegrityError:
        return None

async def auth_user(email: str, password: str) -> Optional[str]:
    user: Optional[Type[User]] = await async_manager.get_or_none(User, email=email)
    if not user: return None
    hashed_password = hashlib.scrypt(password=password.encode(), salt=user.password_salt.encode(), n=16384, r=8, p=1).hex()
    if user.password_hash == hashed_password: 
        return user.secret_token
    return None

async def create_filesystem_root(user: User) -> Optional[FileSystemNode]:
    if await async_manager.execute(FileSystemNode.select().where((FileSystemNode.owner==user) & \
                                                           (FileSystemNode.parent==None))): return None
    return await async_manager.create(FileSystemNode, name='/', owner=user)

async def get_filesystem_root(user: User) -> FileSystemNode:
    return await async_manager.get(FileSystemNode, owner=user, parent=None)

async def is_shared_with(user: User, node: FileSystemNode) -> bool:
    if (await async_manager.get_or_none(SharedNode, shared_with=user, node=node)):
        return True
    owner = await async_manager._get_foreign_key_target(node, 'owner')
    if owner == user:
        return True # more like is shared by
    elif parent := await async_manager._get_foreign_key_target(node, 'parent'):
        return await is_shared_with(user, parent)
    return False

async def list_files(user: User, node: FileSystemNode) -> List[FileSystemNode]:
    if (await check_node_ownership(node, user)) or (await is_shared_with(user, node)):
            return await async_manager._get_backrefs(node, 'children')
    return []

async def add_file(user: User, node: FileSystemNode, name: str, file: File) -> Optional[FileSystemNode]:
    if node.file:
        return None
    return await async_manager.create(FileSystemNode, name=name, parent=node, owner=user, file=file)

async def add_folder(user: User, node: FileSystemNode, name: str) -> Optional[FileSystemNode]:
    if node.file:
        return None
    return await async_manager.create(FileSystemNode, name=name, parent=node, owner=user)

async def file_association(file_path: str, uploader: User, size: int, hash=None) -> File:
    return await async_manager.create(File, real_path=file_path, owner=uploader, size=size, sha256=hash)

async def check_node_ownership(node: FileSystemNode, user: User) -> bool:
    return (await async_manager._get_foreign_key_target(node, 'owner')) == user

async def check_dir_and_ownership(node: FileSystemNode, user: User) -> bool:
    if (await async_manager._get_foreign_key_target(node, 'file')):
        return False
    return await check_node_ownership(node, user)

async def copy_branch(user: User, src: FileSystemNode, dst: FileSystemNode) -> bool:
    if (not dst or not src) or not (await check_dir_and_ownership(dst, user)):
        return False
    
    childs =  await async_manager._get_backrefs(src, 'children')
    if childs:
        got = await add_folder(user, dst, src.name)
        if isinstance(got, FileSystemNode):
            dst = got
    else:
        await add_file(user, dst, src.name, await async_manager._get_foreign_key_target(src, 'file'))
    for c in childs:
        await copy_branch(user, c, dst)
    return True

async def move_node(user: User, node: FileSystemNode, to: FileSystemNode) -> bool:
    if (not await check_node_ownership(node, user)) or (not await check_node_ownership(to, user)):
        return False
    if node == to:
        return False
    node.parent = to
    node.expire_date = None
    await async_manager.update(node)
    return True

async def delete_node(user: User, node: FileSystemNode) -> bool:
    if not (await check_node_ownership(node, user)):
        return False
    if node.expire_date:
        node.expire_date = None
        await async_manager.update(node)
    else:
        node.parent = None
        node.expire_date = datetime.utcnow()
        await async_manager.update(node)
    return True

async def identify_user(token: RAP.Token) -> Optional[User]:
    return await async_manager.get_or_none(User, secret_token=token.token)

async def get_filesystemnode_by_id(user: User, id: int) -> Optional[FileSystemNode]:
    node = await async_manager.get_or_none(FileSystemNode, id=id)
    if not node:
        return None
    if (await check_node_ownership(node, user)) or (await is_shared_with(user, node)):
        return node
    return None

async def get_owner(user, node: FileSystemNode) -> Optional[User]:
    owner = (await async_manager._get_foreign_key_target(node, 'owner'))
    if owner == user or (await is_shared_with(user, node)):
        return owner
    return None

async def get_extended_info_by_id(user: User, id: int) -> Optional[RAP.ExtendedFileInfo]:
    if not (node := (await get_filesystemnode_by_id(user, id))):
        return None
    if not ((await check_node_ownership(node, user)) or (await is_shared_with(user, node))):
        return None
    owner = await get_owner(user, node)
    if not owner:
        return None
    if (file := (await async_manager._get_foreign_key_target(node, 'file'))):
        info = RAP.ExtendedFileInfo(short_info=RAP.FileInfo(display_name=node.name, id=id, size=file.size))
        info.unix_time = file.upload_time
    else:
        info = RAP.ExtendedFileInfo(short_info=RAP.FileInfo(display_name=node.name, id=id))

    info.owner = owner.email
    

    shared_nodes: List[SharedNode] = await async_manager._get_backrefs(node, 'shared_with')
    for n in shared_nodes:
        info.shared_list.append((await async_manager._get_foreign_key_target(n, 'shared_with')).email)
    return info

async def rename_node(user: User, node: FileSystemNode, new_name: str) -> bool:
    if not (await check_node_ownership(node, user)):
        return False
    node.name = new_name
    await async_manager.update(node)
    return True

async def get_user_from_email(email: str) -> Optional[User]:
    return await async_manager.get_or_none(User, email=email)


async def share_node(user: User, to: User, node: FileSystemNode) -> bool:
    if not (await check_node_ownership(node, user)):
        return False
    if (await async_manager.get_or_none(SharedNode, shared_with=to, node=node)):
        return True
    await async_manager.create(SharedNode, shared_with=to, node=node)
    return True

async def remove_share(user: User, who: User, node: FileSystemNode) -> bool:
    if not (await check_node_ownership(node, user)):
        return False
    if not (shared_node := await async_manager.get_or_none(SharedNode, shared_with=who, node=node)):
        return True
    await async_manager.delete(shared_node)
    return True

async def get_pending(user: User) -> List[str]:
    output = []
    for friend_request in (await async_manager._get_backrefs(user, 'friend_requests')):
        output.append((await async_manager._get_foreign_key_target(friend_request, 'sender')).email)
    return output

async def get_friends(user: User) -> List[str]:
    output = []
    friend_relations = await async_manager.execute(Friends.select().where((Friends.user1 == user) | (Friends.user2 == user)))
    for friend_relation in friend_relations:
        if await async_manager._get_foreign_key_target(friend_relation, 'user1') != user:
            output.append((await async_manager._get_foreign_key_target(friend_relation, 'user1')).email)
        else:
            output.append((await async_manager._get_foreign_key_target(friend_relation, 'user2')).email)
    return output

async def is_friends(user: User, other: User) -> Optional[Friends]:
    option1 = await async_manager.get_or_none(Friends, user1=other, user2=user)
    option2 = await async_manager.get_or_none(Friends, user2=other, user1=user)
    if option1:
        return option1
    else:
        return option2

async def send_friend(user: User, who: str) -> bool:
    if not (other := await async_manager.get_or_none(User, email=who)):
        return False
    if await is_friends(user, other):
        return True # already friends
    await async_manager.get_or_create(FriendRequest, sender=user, reciever=other)
    return True

async def accept_friend(user: User, who: str) -> bool:
    if not (other := await async_manager.get_or_none(User, email=who)):
        return False
    if not (relation := await async_manager.get_or_none(FriendRequest, sender=other, reciever=user)):
        return False
    await async_manager.delete(relation)
    await async_manager.create(Friends, user1=other, user2=user)
    return True

async def reject_friend(user: User, who: str) -> bool:
    if not (other := await async_manager.get_or_none(User, email=who)):
        return False
    if not (relation := await async_manager.get_or_none(FriendRequest, sender=other, reciever=user)):
        return False    
    await async_manager.delete(relation)
    return True

async def remove_friend(user: User, who: str) -> bool:
    if not (other := await async_manager.get_or_none(User, email=who)):
        return False
    if not (relation := await is_friends(user, other)):
        return True
    await async_manager.delete(relation)
    return True

async def get_shared_roots(user: User) -> List[FileSystemNode]:
    listed = []
    for shared_node in await async_manager._get_backrefs(user, 'shared_nodes'):
        listed.append(await async_manager._get_foreign_key_target(shared_node, 'node'))
    return listed

async def get_trash(user: User) -> List[FileSystemNode]:
    return await async_manager.execute(FileSystemNode.select().where((FileSystemNode.owner == user) & (FileSystemNode.expire_date != None)))

async def get_paths_for_zip(node: FileSystemNode, maxdepth=10) -> Dict[str, str]:
    """ Goes over a directory to map between each contained file name to it's in system path"""
    result: Dict[str, str] = {}
    async def go_over(node: FileSystemNode, prefix, maxdepth):
        if maxdepth <= 0: return
        maxdepth -= 1
        used_names: Set[str] = set()
        nodes: List[FileSystemNode] = await async_manager.execute(FileSystemNode.select().where(FileSystemNode.parent==node))
        for n in nodes:
            name: str = n.name
            if name in used_names:
                splitted = name.split('.')
                if len(splitted) > 1:
                    splitted[-2] += "({})"
                else:
                    splitted[-1] += "({})"
                
                for i in range(len(splitted)):
                    splitted[i] = slugify(splitted[i])
                
                name = ".".join(splitted)
                count = 1
                while name.format(count) in used_names:
                    count += 1
                name = name.format(count)
            used_names.add(name)
            if not await n.is_folder():
                result[prefix + '\\' + name] = (await async_manager._get_foreign_key_target(n, 'file')).real_path
            else:
                await go_over(n, prefix+'\\'+name, maxdepth)
    await go_over(node, '.\\' + node.name, maxdepth)
    return result
    

async def amain():
    with async_manager.allow_sync():
        user = User.get(email='royadararmy@gmail.com')
        root = await get_filesystem_root(user)
        for n in await list_files(user, root):
            if await n.is_folder():
                print(repr(n))

if __name__ == '__main__':
    LOOP.run_until_complete(amain())
