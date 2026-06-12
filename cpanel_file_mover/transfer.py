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
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import paramiko
from tqdm import tqdm


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Improved regex pattern to support:
# - IPv6 addresses in brackets: [::1]:/path or user@[::1]:/path
# - IPv4 addresses: user@host:/path or host:/path
# - Paths starting with /, ~, or relative paths
# - Avoid matching Windows drive letters (C:/path)
TARGET_RE = re.compile(
    r'^(?:(?P<user>[^@\[\]]+)@)?'  # Optional username (not containing @ or [])
    r'(?:\[(?P<ipv6>[^\]]+)\]|(?P<host>[^:]+))'  # IPv6 in brackets or regular host
    r'(?::(?P<path>.*))?$'  # Optional colon and path
)

# Pattern for Windows drive letters to exclude them
WINDOWS_DRIVE_RE = re.compile(r'^[A-Za-z]:[/\\]')


def parse_target(spec: str) -> Dict[str, Any]:
    """Parse a spec like `user@host:/path` or a local path.

    Returns dict with keys: type ('remote'|'local'), user, host, path
    
    Supports:
    - IPv6 addresses: user@[::1]:/path or [::1]:/path
    - IPv4 addresses: user@host:/path or host:/path
    - Absolute paths: /home/user/file
    - Home directory paths: ~/file or ~user/file
    - Relative paths: ./file or file.txt
    - Excludes Windows drive letters: C:/path
    """
    # Check for Windows drive letters first
    if WINDOWS_DRIVE_RE.match(spec):
        return {"type": "local", "path": os.path.abspath(spec)}
    
    m = TARGET_RE.match(spec)
    if m:
        host = m.group("host") or m.group("ipv6")
        path = m.group("path")
        
        # Only consider it remote if there's a host and a path
        if host and path is not None:
            # Expand user home directory in path
            if path.startswith('~'):
                path = os.path.expanduser(path)
            
            return {
                "type": "remote",
                "user": m.group("user") or None,
                "host": host,
                "path": path,
            }
    
    # Local path - expand user home directory
    expanded_path = os.path.expanduser(spec)
    return {"type": "local", "path": os.path.abspath(expanded_path)}


class SFTPConnection:
    """SFTP connection manager with improved error handling and logging."""
    
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
        """Establish SSH and SFTP connection with proper error handling."""
        logger.info(f"Connecting to {self.host}:{self.port} as {self.username or 'anonymous'}")
        
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        pkey = None
        if self.pkey_path:
            expanded_path = os.path.expanduser(self.pkey_path)
            if not os.path.exists(expanded_path):
                raise FileNotFoundError(f"Private key file not found: {expanded_path}")
            
            logger.debug(f"Loading private key from {expanded_path}")
            try:
                # Try different key types
                for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey]:
                    try:
                        pkey = key_class.from_private_key_file(expanded_path)
                        logger.debug(f"Successfully loaded key as {key_class.__name__}")
                        break
                    except (paramiko.SSHException, ValueError):
                        continue
                
                if pkey is None:
                    raise ValueError(f"Unable to load private key from {expanded_path}")
                    
            except Exception as e:
                logger.error(f"Failed to load private key: {e}")
                raise
        
        try:
            self.client.connect(
                self.host, 
                port=self.port, 
                username=self.username, 
                password=self.password, 
                pkey=pkey, 
                timeout=self.timeout,
                allow_agent=True,
                look_for_keys=True
            )
            self.sftp = self.client.open_sftp()
            logger.info(f"Successfully connected to {self.host}")
        except paramiko.AuthenticationException as e:
            logger.error(f"Authentication failed for {self.username}@{self.host}: {e}")
            self.close()
            raise
        except paramiko.SSHException as e:
            logger.error(f"SSH connection error to {self.host}: {e}")
            self.close()
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to {self.host}: {e}")
            self.close()
            raise

    def close(self):
        """Close SFTP and SSH connections with proper error handling."""
        logger.debug(f"Closing connection to {self.host}")
        try:
            if self.sftp:
                self.sftp.close()
                logger.debug("SFTP connection closed")
        except Exception as e:
            logger.warning(f"Error closing SFTP connection: {e}")
        try:
            if self.client:
                self.client.close()
                logger.debug("SSH connection closed")
        except Exception as e:
            logger.warning(f"Error closing SSH connection: {e}")

    def exists(self, path: str) -> bool:
        """Check if a remote path exists."""
        try:
            self.sftp.stat(path)
            return True
        except IOError:
            return False
        except Exception as e:
            logger.warning(f"Error checking existence of {path}: {e}")
            return False

    def isdir(self, path: str) -> bool:
        """Check if a remote path is a directory."""
        try:
            return stat.S_ISDIR(self.sftp.stat(path).st_mode)
        except Exception as e:
            logger.warning(f"Error checking if {path} is directory: {e}")
            return False

    def mkdir_p(self, remote_directory: str):
        """Create remote directories recursively with error handling."""
        logger.debug(f"Creating remote directory: {remote_directory}")
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
                logger.debug(f"Created directory: {d}")
            except Exception as e:
                logger.warning(f"Failed to create directory {d}: {e}")

    def listdir_attr(self, path: str):
        """List directory contents with attributes and error handling."""
        try:
            return self.sftp.listdir_attr(path)
        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            raise

    def download_file(self, remote_path: str, local_path: str):
        """Download a file from remote to local with progress tracking."""
        logger.info(f"Downloading {remote_path} to {local_path}")
        try:
            size = self.sftp.stat(remote_path).st_size
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            with tqdm(total=size, unit='B', unit_scale=True, desc=os.path.basename(remote_path)) as pbar:
                def cb(transferred, _):
                    pbar.update(transferred - pbar.n)

                self.sftp.get(remote_path, local_path, callback=cb)
            
            logger.debug(f"Successfully downloaded {remote_path}")
        except Exception as e:
            logger.error(f"Error downloading {remote_path}: {e}")
            raise

    def upload_file(self, local_path: str, remote_path: str):
        """Upload a file from local to remote with progress tracking."""
        logger.info(f"Uploading {local_path} to {remote_path}")
        try:
            size = os.path.getsize(local_path)
            rdir = os.path.dirname(remote_path)
            self.mkdir_p(rdir)
            
            with tqdm(total=size, unit='B', unit_scale=True, desc=os.path.basename(local_path)) as pbar:
                def cb(transferred, _):
                    pbar.update(transferred - pbar.n)

                self.sftp.put(local_path, remote_path, callback=cb)
            
            logger.debug(f"Successfully uploaded {local_path}")
        except Exception as e:
            logger.error(f"Error uploading {local_path}: {e}")
            raise

    def download_dir(self, remote_dir: str, local_dir: str):
        """Download a directory recursively from remote to local."""
        logger.info(f"Downloading directory {remote_dir} to {local_dir}")
        try:
            os.makedirs(local_dir, exist_ok=True)
            for entry in self.listdir_attr(remote_dir):
                rname = entry.filename
                rpath = os.path.join(remote_dir, rname)
                lpath = os.path.join(local_dir, rname)
                if stat.S_ISDIR(entry.st_mode):
                    self.download_dir(rpath, lpath)
                else:
                    self.download_file(rpath, lpath)
            logger.debug(f"Successfully downloaded directory {remote_dir}")
        except Exception as e:
            logger.error(f"Error downloading directory {remote_dir}: {e}")
            raise

    def upload_dir(self, local_dir: str, remote_dir: str):
        """Upload a directory recursively from local to remote."""
        logger.info(f"Uploading directory {local_dir} to {remote_dir}")
        try:
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
            logger.debug(f"Successfully uploaded directory {local_dir}")
        except Exception as e:
            logger.error(f"Error uploading directory {local_dir}: {e}")
            raise


def transfer(source: str, dest: str, src_auth: dict = None, dst_auth: dict = None):
    """Transfer from source to dest. Both can be local paths or remote specs.

    Example remote spec: user@host:/path
    
    Args:
        source: Source path (local or remote spec)
        dest: Destination path (local or remote spec)
        src_auth: Authentication dict for source with keys: user, password, pkey
        dst_auth: Authentication dict for destination with keys: user, password, pkey
    
    Raises:
        FileNotFoundError: If source doesn't exist or private key file not found
        paramiko.AuthenticationException: If authentication fails
        Exception: For other transfer errors
    """
    logger.info(f"Starting transfer from {source} to {dest}")
    
    src_auth = src_auth or {}
    dst_auth = dst_auth or {}

    s = parse_target(source)
    d = parse_target(dest)
    
    logger.debug(f"Source parsed as: {s['type']} - {s.get('host', 'local')}")
    logger.debug(f"Destination parsed as: {d['type']} - {d.get('host', 'local')}")

    tmpdir = tempfile.mkdtemp(prefix="cpfilemove_")
    logger.debug(f"Using temporary directory: {tmpdir}")
    
    try:
        # Download source into tmpdir (if remote)
        if s['type'] == 'local':
            # copy local into tmpdir
            src_path = s['path']
            if not os.path.exists(src_path):
                raise FileNotFoundError(f"Source path does not exist: {src_path}")
            
            logger.info(f"Copying local source: {src_path}")
            if os.path.isdir(src_path):
                dst_tmp = os.path.join(tmpdir, os.path.basename(src_path.rstrip('/')))
                shutil.copytree(src_path, dst_tmp)
            else:
                shutil.copy2(src_path, tmpdir)
        else:
            sconn = SFTPConnection(
                host=s['host'], 
                username=s.get('user') or src_auth.get('user'), 
                password=src_auth.get('password'), 
                pkey_path=src_auth.get('pkey')
            )
            sconn.connect()
            rpath = s['path']
            
            if not sconn.exists(rpath):
                sconn.close()
                raise FileNotFoundError(f"Remote source path does not exist: {rpath}")
            
            if sconn.isdir(rpath):
                logger.info(f"Downloading remote directory: {rpath}")
                sconn.download_dir(rpath, os.path.join(tmpdir, os.path.basename(rpath.rstrip('/'))))
            else:
                logger.info(f"Downloading remote file: {rpath}")
                sconn.download_file(rpath, os.path.join(tmpdir, os.path.basename(rpath)))
            sconn.close()

        # Upload from tmpdir to destination
        if d['type'] == 'local':
            dest_path = d['path']
            logger.info(f"Copying to local destination: {dest_path}")
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
            dconn = SFTPConnection(
                host=d['host'], 
                username=d.get('user') or dst_auth.get('user'), 
                password=dst_auth.get('password'), 
                pkey_path=dst_auth.get('pkey')
            )
            dconn.connect()
            rbase = d['path']
            logger.info(f"Uploading to remote destination: {rbase}")
            
            # if tmpdir contains a single entry that is a dir, upload that into rbase
            for entry in os.listdir(tmpdir):
                lpath = os.path.join(tmpdir, entry)
                if os.path.isdir(lpath):
                    dconn.upload_dir(lpath, os.path.join(rbase, entry))
                else:
                    dconn.upload_file(lpath, os.path.join(rbase, entry))
            dconn.close()

        logger.info("Transfer completed successfully")
        
    except Exception as e:
        logger.error(f"Transfer failed: {e}")
        raise
    finally:
        logger.debug(f"Cleaning up temporary directory: {tmpdir}")
        shutil.rmtree(tmpdir, ignore_errors=True)
