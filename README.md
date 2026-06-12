# cPanel File Mover — انتقال فایل بین هاست‌های cPanel

این پروژه یک ابزار خط فرمان ساده و قابل اعتماد برای جابجایی فایل‌ها بین دو هاست (مثل هاست‌های cPanel) از طریق SFTP فراهم می‌کند. ابزار به‌صورت بازگشتی پوشه‌ها و فایل‌ها را منتقل می‌کند و پیشرفت را نمایش می‌دهد.

---

# cPanel File Mover — Move files between cPanel hosts

This project is a small CLI tool to move files and directories between two hosts (for example, cPanel servers) using SFTP. It downloads source data into a temporary directory and uploads it to the destination.

## Features / ویژگی‌ها

- **Recursive directory transfers** / انتقال بازگشتی دایرکتوری
- **Password or private-key authentication** / پشتیبانی از رمز یا کلید خصوصی
- **Progress bars with `tqdm`** / نمایش پیشرفت با `tqdm`
- **IPv6 support** / پشتیبانی از IPv6
- **Multiple key types (RSA, Ed25519, ECDSA, DSS)** / پشتیبانی از انواع کلیدهای SSH
- **Comprehensive error handling and logging** / مدیریت خطا و لاگ‌گیری کامل
- **Windows path support** / پشتیبانی از مسیرهای ویندوز

## Requirements / نیازمندی‌ها

- Python 3.8+
- See `requirements.txt`

## Installation / نصب

```bash
pip install -r requirements.txt
```

Or install as a package:

```bash
pip install -e .
```

## Quick examples / مثال‌های سریع

### 1) Transfer from remote to remote (password prompts):
```bash
python cli.py user1@host1:/var/www/html user2@host2:/home/user2/www
```

### 2) Use private keys:
```bash
python cli.py --src-key ~/.ssh/id_rsa --dst-key ~/.ssh/id_rsa \
    user1@host1:/path user2@host2:/dest
```

### 3) Force password prompt explicitly (secure - not visible in process list):
```bash
python cli.py --src-pass PROMPT --dst-pass PROMPT \
    user1@host1:/path user2@host2:/dest
```

### 4) IPv6 support:
```bash
python cli.py user@[::1]:/path/to/file /local/destination
python cli.py user@[2001:db8::1]:/home/user/data ~/backup
```

### 5) Local to remote transfer:
```bash
python cli.py /local/path user@host:/remote/destination
```

### 6) Remote to local transfer:
```bash
python cli.py user@host:/remote/path /local/destination
```

### 7) Verbose output for debugging:
```bash
python cli.py -v user@host:/path /local/dest
```

## Command-line options / گزینه‌های خط فرمان

```
positional arguments:
  source               Source spec: user@host:/path or /local/path
  dest                 Dest spec: user@host:/path or /local/path

options:
  -h, --help           show this help message and exit
  --src-key SRC_KEY    Private key file for source
  --dst-key DST_KEY    Private key file for dest
  --src-user SRC_USER  Username for source (if not in source spec)
  --dst-user DST_USER  Username for dest (if not in dest spec)
  --src-pass SRC_PASS  Password for source (use PROMPT to be prompted securely)
  --dst-pass DST_PASS  Password for dest (use PROMPT to be prompted securely)
  -v, --verbose        Enable verbose output
  --src-port SRC_PORT  SSH port for source (default: 22)
  --dst-port DST_PORT  SSH port for dest (default: 22)
```

## Path specifications / مشخصات مسیرها

The tool supports various path formats:

| Format | Example | Type |
|--------|---------|------|
| Absolute local | `/home/user/file.txt` | Local |
| Relative local | `./file.txt` | Local |
| Home directory | `~/file.txt` | Local |
| Windows path | `C:/Users/file.txt` | Local |
| Remote IPv4 | `user@192.168.1.1:/path` | Remote |
| Remote hostname | `user@example.com:/path` | Remote |
| Remote IPv6 | `user@[::1]:/path` | Remote |
| Remote with tilde | `user@host:~/file` | Remote |

## Security notes / نکات امنیتی

- **Never pass passwords directly on command line** - they may be visible in process lists
- Use `--src-pass PROMPT` or `--dst-pass PROMPT` for secure password entry
- Prefer SSH keys over passwords when possible
- Private key files are validated before use

## API Usage / استفاده از API

```python
from cpanel_file_mover import transfer

# Simple transfer
transfer('user@host:/remote/path', '/local/dest')

# With authentication
transfer(
    'user@host:/path',
    '/local/dest',
    src_auth={'password': 'secret', 'pkey': '~/.ssh/id_rsa'},
    dst_auth={'password': 'secret2'}
)
```

## Running tests / اجرای تست‌ها

```bash
python -m unittest discover -s tests -v
```

## Logging / لاگ‌گیری

The tool uses Python's logging module. Enable verbose mode with `-v` flag or configure logging programmatically:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## License / مجوز

MIT License - see LICENSE file

## Contributing / مشارکت

Contributions are welcome! Please feel free to submit issues and pull requests.
