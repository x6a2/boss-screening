
import os, site, sys

# First, drop system-sites related paths.
original_sys_path = sys.path[:]
known_paths = set()
for path in {'d:\\ti\\learn\\creat place\\boss-screening\\.\\.venv\\lib\\site-packages', 'd:\\ti\\learn\\creat place\\boss-screening\\.\\.venv'}:
    site.addsitedir(path, known_paths=known_paths)
system_paths = set(
    os.path.normcase(path)
    for path in sys.path[len(original_sys_path):]
)
original_sys_path = [
    path for path in original_sys_path
    if os.path.normcase(path) not in system_paths
]
sys.path = original_sys_path

# Second, add lib directories.
# ensuring .pth file are processed.
for path in ['D:\\Ti\\learn\\creat place\\boss-screening\\pip-build-env-txnovpd1\\overlay\\Lib\\site-packages', 'D:\\Ti\\learn\\creat place\\boss-screening\\pip-build-env-txnovpd1\\normal\\Lib\\site-packages']:
    assert not path in sys.path
    site.addsitedir(path)
