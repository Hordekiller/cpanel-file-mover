#!/usr/bin/env python3
"""CLI for cPanel File Mover - Transfer files between hosts via SFTP."""
import argparse
import getpass
import sys
import logging

from cpanel_file_mover import transfer


# Configure logging for CLI
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    p = argparse.ArgumentParser(
        description="Transfer files between two hosts (supports SFTP)",
        epilog="""
Examples:
  # Transfer from remote to remote (password prompts):
  python cli.py user1@host1:/var/www/html user2@host2:/home/user2/www

  # Use private keys:
  python cli.py --src-key ~/.ssh/id_rsa --dst-key ~/.ssh/id_rsa user1@host1:/path user2@host2:/dest

  # Force password prompt explicitly:
  python cli.py --src-pass PROMPT --dst-pass PROMPT user1@host1:/path user2@host2:/dest

  # IPv6 support:
  python cli.py user@[::1]:/path /local/dest
        """
    )
    p.add_argument('source', help='Source spec: user@host:/path or /local/path')
    p.add_argument('dest', help='Dest spec: user@host:/path or /local/path')
    p.add_argument('--src-key', help='Private key file for source')
    p.add_argument('--dst-key', help='Private key file for dest')
    p.add_argument('--src-user', help='Username for source (if not in source spec)')
    p.add_argument('--dst-user', help='Username for dest (if not in dest spec)')
    p.add_argument('--src-pass', help='Password for source (use PROMPT to be prompted securely)')
    p.add_argument('--dst-pass', help='Password for dest (use PROMPT to be prompted securely)')
    p.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    p.add_argument('--src-port', type=int, default=22, help='SSH port for source (default: 22)')
    p.add_argument('--dst-port', type=int, default=22, help='SSH port for dest (default: 22)')

    args = p.parse_args()

    # Set log level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    src_auth = {}
    dst_auth = {}
    
    if args.src_key:
        src_auth['pkey'] = args.src_key
    if args.dst_key:
        dst_auth['pkey'] = args.dst_key
    
    if args.src_user:
        src_auth['user'] = args.src_user
    if args.dst_user:
        dst_auth['user'] = args.dst_user

    # Prompt for passwords if provided as flag value 'PROMPT'
    # This prevents passwords from appearing in process lists
    if args.src_pass == 'PROMPT':
        src_auth['password'] = getpass.getpass(f"Password for source ({args.source}): ")
    elif args.src_pass:
        logger.warning("Warning: Password provided via command line may be visible in process list")
        src_auth['password'] = args.src_pass

    if args.dst_pass == 'PROMPT':
        dst_auth['password'] = getpass.getpass(f"Password for dest ({args.dest}): ")
    elif args.dst_pass:
        logger.warning("Warning: Password provided via command line may be visible in process list")
        dst_auth['password'] = args.dst_pass

    try:
        logger.info(f"Starting transfer: {args.source} -> {args.dest}")
        transfer(args.source, args.dest, src_auth=src_auth, dst_auth=dst_auth)
        logger.info("Transfer completed successfully")
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nAborted', file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Transfer failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
