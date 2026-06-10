"""Reliable SFTP transfer utilities.

This module provides `SFTPConnection` and `transfer()` which downloads
from a source (local or remote SFTP) into a temporary directory and
uploads to a destination (local or remote SFTP). It handles recursive
directories, private keys, and password prompting.
"""
import os
import stat
import tempfile
import shutil
import re
from pathlib import Path
from typing import Optional

import paramiko
from tqdm import tqdm


TARGET_RE = re.compile(r'^(?:(?P<user>[^@]+)@)?(?P<host>[^:]+):(?P<path>/.*)$')


def parse_target(spec: str):
    """Parse a spec like `user@host:/path` or a local path.

    Returns dict with keys: type ('remote'|'local'), user, host, path
    """
    m = TARGET_RE.match(spec)
    if m:
        return {
            "type": "remote",
            "user": m.group("user") or None,
            "host": m.group("host"),
            "path": m.group("path"),
        }
    return {"type": "local", "path": os.path.abspath(spec)}


class SFTPConnection:
    def __init__(self, host: str, username: Optional[str] = None, password: Optional[str] = None, pkey_path: Optional[str] = None, port: int = 22, timeout: int = 30):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.pkey_path = pkey_path
        self.timeout = timeout
        self.client: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = None
        if self.pkey_path:
            pkey = paramiko.RSAKey.from_private_key_file(os.path.expanduser(self.pkey_path))
        try:
            self.client.connect(self.host, port=self.port, username=self.username, password=self.password, pkey=pkey, timeout=self.timeout)
            self.sftp = self.client.open_sftp()
        except Exception:
            self.close()
            raise

    def close(self):
        try:
            if self.sftp:
                self.sftp.close()
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass

    def exists(self, path: str) -> bool:
        try:
            self.sftp.stat(path)
            return True
        except IOError:
            return False

    def isdir(self, path: str) -> bool:
        try:
            return stat.S_ISDIR(self.sftp.stat(path).st_mode)
        except Exception:
            return False

    def mkdir_p(self, remote_directory: str):
        # Creates remote directories recursively
        dirs = []
        cur = remote_directory.rstrip("/")
        while cur and cur != "/":
            try:
                self.sftp.stat(cur)
                break
            except IOError:
                dirs.append(cur)
                cur = os.path.dirname(cur)
        for d in reversed(dirs):
            try:
                self.sftp.mkdir(d)
            except Exception:
                pass

    def listdir_attr(self, path: str):
        return self.sftp.listdir_attr(path)

    def download_file(self, remote_path: str, local_path: str):
        size = self.sftp.stat(remote_path).st_size
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with tqdm(total=size, unit='B', unit_scale=True, desc=os.path.basename(remote_path)) as pbar:
            def cb(transferred, _):
                pbar.update(transferred - pbar.n)

            self.sftp.get(remote_path, local_path, callback=cb)

    def upload_file(self, local_path: str, remote_path: str):
        size = os.path.getsize(local_path)
        rdir = os.path.dirname(remote_path)
        self.mkdir_p(rdir)
        with tqdm(total=size, unit='B', unit_scale=True, desc=os.path.basename(local_path)) as pbar:
            def cb(transferred, _):
                pbar.update(transferred - pbar.n)

            self.sftp.put(local_path, remote_path, callback=cb)

    def download_dir(self, remote_dir: str, local_dir: str):
        os.makedirs(local_dir, exist_ok=True)
        for entry in self.listdir_attr(remote_dir):
            rname = entry.filename
            rpath = os.path.join(remote_dir, rname)
            lpath = os.path.join(local_dir, rname)
            if stat.S_ISDIR(entry.st_mode):
                self.download_dir(rpath, lpath)
            else:
                self.download_file(rpath, lpath)

    def upload_dir(self, local_dir: str, remote_dir: str):
        for root, dirs, files in os.walk(local_dir):
            rel = os.path.relpath(root, local_dir)
            if rel == '.':
                rroot = remote_dir
            else:
                rroot = os.path.join(remote_dir, rel)
            self.mkdir_p(rroot)
            for f in files:
                lpath = os.path.join(root, f)
                rpath = os.path.join(rroot, f)
                self.upload_file(lpath, rpath)


def transfer(source: str, dest: str, src_auth: dict = None, dst_auth: dict = None):
    """Transfer from source to dest. Both can be local paths or remote specs.

    Example remote spec: user@host:/path
    """
    src_auth = src_auth or {}
    dst_auth = dst_auth or {}

    s = parse_target(source)
    d = parse_target(dest)

    tmpdir = tempfile.mkdtemp(prefix="cpfilemove_")
    try:
        # Download source into tmpdir (if remote)
        if s['type'] == 'local':
            # copy local into tmpdir
            src_path = s['path']
            if os.path.isdir(src_path):
                dst_tmp = os.path.join(tmpdir, os.path.basename(src_path.rstrip('/')))
                shutil.copytree(src_path, dst_tmp)
            else:
                shutil.copy2(src_path, tmpdir)
        else:
            sconn = SFTPConnection(host=s['host'], username=s.get('user') or src_auth.get('user'), password=src_auth.get('password'), pkey_path=src_auth.get('pkey'))
            sconn.connect()
            rpath = s['path']
            # ensure exists
            if sconn.isdir(rpath):
                sconn.download_dir(rpath, os.path.join(tmpdir, os.path.basename(rpath.rstrip('/'))))
            else:
                sconn.download_file(rpath, os.path.join(tmpdir, os.path.basename(rpath)))
            sconn.close()

        # Upload from tmpdir to destination
        if d['type'] == 'local':
            dest_path = d['path']
            os.makedirs(dest_path, exist_ok=True)
            for item in os.listdir(tmpdir):
                srcp = os.path.join(tmpdir, item)
                dstp = os.path.join(dest_path, item)
                if os.path.isdir(srcp):
                    if os.path.exists(dstp):
                        shutil.rmtree(dstp)
                    shutil.copytree(srcp, dstp)
                else:
                    shutil.copy2(srcp, dstp)
        else:
            dconn = SFTPConnection(host=d['host'], username=d.get('user') or dst_auth.get('user'), password=dst_auth.get('password'), pkey_path=dst_auth.get('pkey'))
            dconn.connect()
            rbase = d['path']
            # if tmpdir contains a single entry that is a dir, upload that into rbase
            for entry in os.listdir(tmpdir):
                lpath = os.path.join(tmpdir, entry)
                if os.path.isdir(lpath):
                    dconn.upload_dir(lpath, os.path.join(rbase, entry))
                else:
                    dconn.upload_file(lpath, os.path.join(rbase, entry))
            dconn.close()

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
