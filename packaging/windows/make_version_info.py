"""Write version_info.txt (the Details tab of TCsOffice.exe) from office/version.py."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
version = re.search(r'__version__ = "([^"]+)"', (ROOT / "office/version.py").read_text()).group(1)
nums = (tuple(int(n) for n in version.split(".")) + (0, 0, 0, 0))[:4]
(Path(__file__).parent / "version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'TCsM'),
    StringStruct('FileDescription', 'TCsOffice'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('ProductName', 'TCsOffice'),
    StringStruct('ProductVersion', '{version}')])]),
   VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""")
print(version)
