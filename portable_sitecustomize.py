"""Private runtime policy, also applied when VSScript embeds Python."""
import sys

sys.dont_write_bytecode = True
