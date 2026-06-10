# cPanel File Mover — انتقال فایل بین هاست‌های cPanel

این پروژه یک ابزار خط فرمان ساده و قابل اعتماد برای جابجایی فایل‌ها بین دو هاست (مثل هاست‌های cPanel) از طریق SFTP فراهم می‌کند. ابزار به‌صورت بازگشتی پوشه‌ها و فایل‌ها را منتقل می‌کند و پیشرفت را نمایش می‌دهد.

---

# cPanel File Mover — Move files between cPanel hosts

This project is a small CLI tool to move files and directories between two hosts (for example, cPanel servers) using SFTP. It downloads source data into a temporary directory and uploads it to the destination.

Features / ویژگی‌ها:
- Recursive directory transfers / انتقال بازگشتی دایرکتوری
- Password or private-key authentication / پشتیبانی از رمز یا کلید خصوصی
- Progress bars with `tqdm` / نمایش پیشرفت با `tqdm`

Requirements / نیازمندی‌ها:
- Python 3.8+
- See `requirements.txt`

Quick examples / مثال‌های سریع:

1) Transfer from remote to remote (password prompts):

```bash
python cli.py user1@host1:/var/www/html user2@host2:/home/user2/www
```

2) Use private keys:

```bash
python cli.py --src-key ~/.ssh/id_rsa --dst-key ~/.ssh/id_rsa user1@host1:/path user2@host2:/dest
```

3) Force password prompt explicitly:

```bash
python cli.py --src-pass PROMPT --dst-pass PROMPT user1@host1:/path user2@host2:/dest
```

See `python cli.py -h` for more options.

