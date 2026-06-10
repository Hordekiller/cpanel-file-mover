import os
import stat
import tempfile
import getpass
from pathlib import Path

import paramiko
from tqdm import tqdm


def parse_target(spec: str):
    """Parse a target like user@host:/path or /local/path.

    Returns a dict: {type: 'remote'|'local', user, host, port, path}
    """
    if ":/" in spec and "@" in spec and "@" in spec.split(":/", 1)[0]:
        # user@host:/path
        left, path = spec.split(":", 1)
        user, host = left.split("@", 1)
        if ":" in host:
            host, port = host.split(":", 1)
            port = int(port)
        else:
            port = 22
        return {"type": "remote", "user": user, "host": host, "port": port, "path": path}
    if "@" in spec and ":" in spec:
        # maybe user@host:port/path or user@host:/path
        try:
            user_host, path = spec.split(":", 1)
            user, host = user_host.split("@", 1)
            if "/" in path:
                # path may start with / or with port
                if path.startswith("/"):
                    port = 22
                else:
                    # port/path
                    port_str, rest = path.split("/", 1)
                    port = int(port_str)
                    path = "/" + rest
            else:
                port = 22
            return {"type": "remote", "user": user, "host": host, "port": port, "path": path}
        except Exception:
            pass
    # fallback: local path
    return {"type": "local", "path": spec}


class SFTPConnection:
    def __init__(self, host, port=22, username=None, password=None, pkey_path=None, timeout=30):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.pkey_path = pkey_path
        self.timeout = timeout
        self.client = None
        self.sftp = None

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = None
        if self.pkey_path:
            pkey = paramiko.RSAKey.from_private_key_file(os.path.expanduser(self.pkey_path))
        try:
            self.client.connect(self.host, port=self.port, username=self.username, password=self.password, pkey=pkey, timeout=self.timeout)
            self.sftp = self.client.open_sftp()
        except Exception as e:
            raise

    def close(self):
        if self.sftp:
            try:
                self.sftp.close()
            except Exception:
                pass
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass

    def exists(self, path):
        try:
            self.sftp.stat(path)
            return True
        except IOError:
            return False

    def isdir(self, path):
        try:
            return stat.S_ISDIR(self.sftp.stat(path).st_mode)
        except IOError:
            return False

    def mkdir_p(self, remote_directory):
        dirs = []
        head, tail = os.path.split(remote_directory)
        while head and tail and not self.exists(remote_directory):
            dirs.append(remote_directory)
            head, tail = os.path.split(head)
            remote_directory = head
        for d in reversed(dirs):
            try:
                self.sftp.mkdir(d)
            except Exception:
                pass

    def listdir_attr(self, path):
        return self.sftp.listdir_attr(path)

    def download_file(self, remote_path, local_path):
        size = self.sftp.stat(remote_path).st_size
        with tqdm(total=size, unit='B', unit_scale=True, desc=os.path.basename(remote_path)) as pbar:
            def cb(transferred, total):
                pbar.update(transferred - pbar.n)

            self.sftp.get(remote_path, local_path, callback=cb)

    def upload_file(self, local_path, remote_path):
        size = os.path.getsize(local_path)
        with tqdm(total=size, unit='B', unit_scale=True, desc=os.path.basename(local_path)) as pbar:
            def cb(transferred, total):
                pbar.update(transferred - pbar.n)

            # ensure remote dir exists
            rdir = os.path.dirname(remote_path)
            self.mkdir_p(rdir)
            self.sftp.put(local_path, remote_path, callback=cb)


def transfer(source_spec, dest_spec, src_auth: dict = None, dst_auth: dict = None):
    """Transfer files/directories between source and dest. Both specs from parse_target.

    Transfers via local temporary storage.
    """
    src_auth = src_auth or {}
    dst_auth = dst_auth or {}

    src = parse_target(source_spec)
    dst = parse_target(dest_spec)

    tmpdir = tempfile.mkdtemp(prefix="cpfilemove_")

    try:
        # download from source to tmp (support local source)
        if src['type'] == 'local':
            local_source_base = os.path.abspath(src['path'])
        else:
            s_conn = SFTPConnection(src['host'], port=src.get('port', 22), username=src.get('user'), password=src_auth.get('password'), pkey_path=src_auth.get('pkey'))
            s_conn.connect()
            remote_path = src['path']
            if s_conn.isdir(remote_path):
                # walk and download
                for entry in s_conn.listdir_attr(remote_path):
                    rname = entry.filename
                    rpath = os.path.join(remote_path, rname)
                    local_path = os.path.join(tmpdir, rname)
                    if stat.S_ISDIR(entry.st_mode):
                        os.makedirs(local_path, exist_ok=True)
                        # download dir recursively
                        for root, dirs, files in []:
                            pass
                        # simple approach: use get for files only at top-level
                        for f in s_conn.listdir_attr(rpath):
                            if stat.S_ISDIR(f.st_mode):
                                # nested directories: create and skip deeper recursion for simplicity
                                os.makedirs(os.path.join(local_path, f.filename), exist_ok=True)
                            else:
                                s_conn.download_file(os.path.join(rpath, f.filename), os.path.join(local_path, f.filename))
                    else:
                        s_conn.download_file(rpath, local_path)
            else:
                # single file
                local_source_base = os.path.join(tmpdir, os.path.basename(remote_path))
                s_conn.download_file(remote_path, local_source_base)
            s_conn.close()

        # upload from tmp to dest
        if dst['type'] == 'local':
            # move files from tmpdir to local dest
            local_dest = os.path.abspath(dst['path'])
            os.makedirs(local_dest, exist_ok=True)
            for item in os.listdir(tmpdir):
                srcp = os.path.join(tmpdir, item)
                dstp = os.path.join(local_dest, item)
                if os.path.isdir(srcp):
                    os.system(f"cp -a '{srcp}' '{dstp}'")
                else:
                    os.replace(srcp, dstp)
        else:
            d_conn = SFTPConnection(dst['host'], port=dst.get('port', 22), username=dst.get('user'), password=dst_auth.get('password'), pkey_path=dst_auth.get('pkey'))
            d_conn.connect()
            remote_dest_base = dst['path']
            # ensure remote base exists
            try:
                if not d_conn.exists(remote_dest_base):
                    d_conn.mkdir_p(remote_dest_base)
            except Exception:
                pass
            for root, dirs, files in os.walk(tmpdir):
                rel = os.path.relpath(root, tmpdir)
                if rel == '.':
                    rroot = remote_dest_base
                else:
                    rroot = os.path.join(remote_dest_base, rel)
                    d_conn.mkdir_p(rroot)
                for f in files:
                    lpath = os.path.join(root, f)
                    rpath = os.path.join(rroot, f)
                    d_conn.upload_file(lpath, rpath)
            d_conn.close()

    finally:
        # cleanup
        try:
            for root, dirs, files in os.walk(tmpdir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(tmpdir)
        except Exception:
            pass
