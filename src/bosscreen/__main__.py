"""支持 `python -m bosscreen ...`，这样没装包也能直接跑。"""

from .cli import main

raise SystemExit(main())
