"""Which build this is and where updates come from.

The release workflow overwrites __version__ with the build's version
(VERSION file + the run number, e.g. 1.0.17) before packaging.
"""
__version__ = "1.1.0"

# The GitHub repository whose Releases the built-in updater watches.
UPDATE_REPO = "TCsM23/TCsMOffice"
