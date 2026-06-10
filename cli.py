#!/usr/bin/env python3
import argparse
import getpass
import sys

from cpanel_file_mover import transfer


def main():
    p = argparse.ArgumentParser(description="Transfer files between two hosts (supports SFTP)")
    p.add_argument('source', help='Source spec: user@host:/path or /local/path')
    p.add_argument('dest', help='Dest spec: user@host:/path or /local/path')
    p.add_argument('--src-key', help='Private key file for source')
    p.add_argument('--dst-key', help='Private key file for dest')
    p.add_argument('--src-pass', help='Password for source (if omitted, prompted)')
    p.add_argument('--dst-pass', help='Password for dest (if omitted, prompted)')

    args = p.parse_args()

    src_auth = {}
    dst_auth = {}
    if args.src_key:
        src_auth['pkey'] = args.src_key
    if args.dst_key:
        dst_auth['pkey'] = args.dst_key

    # prompt for passwords if provided as flag value 'PROMPT'
    if args.src_pass == 'PROMPT':
        src_auth['password'] = getpass.getpass(f"Password for source ({args.source}): ")
    elif args.src_pass:
        src_auth['password'] = args.src_pass

    if args.dst_pass == 'PROMPT':
        dst_auth['password'] = getpass.getpass(f"Password for dest ({args.dest}): ")
    elif args.dst_pass:
        dst_auth['password'] = args.dst_pass

    try:
        transfer(args.source, args.dest, src_auth=src_auth, dst_auth=dst_auth)
    except KeyboardInterrupt:
        print('\nAborted', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
