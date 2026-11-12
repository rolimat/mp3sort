import sys

from sorter.gui import main, self_check

if "--self-check" in sys.argv[1:]:
    sys.exit(self_check())
main()
