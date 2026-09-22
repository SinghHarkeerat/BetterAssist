"""Create private admin credentials outside the public repository."""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engagement import configure_admin

if __name__ == '__main__':
    code = getpass.getpass('Admin login code (hidden): ')
    if len(code) < 6:
        raise SystemExit('Use at least six characters.')
    if code != getpass.getpass('Repeat login code: '):
        raise SystemExit('Codes did not match.')
    configure_admin(code)
    print('Admin credentials saved outside the website. Existing admin sessions were signed out.')
