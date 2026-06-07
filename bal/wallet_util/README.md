## README

### Overview
This tool provides two entry points: a CLI script (bal_wallet_utils.py) and a Qt GUI script (bal_wallet_utils_qt.py) that operate against an Electrum source tree.

### Installation / Preparation
1. Copy both files into the Electrum project root (the folder that contains the Electrum source package):
   - bal_wallet_utils.py
   - bal_wallet_utils_qt.py

2. Activate the Electrum Python environment (the virtualenv used to run Electrum). Example (PowerShell, adjust path to your venv):
```
.\env\Scripts\Activate.ps1
```
or (cmd):
```
env\Scripts\activate.bat
```

### Running
- CLI version:
```
python bal_wallet_utils.py
```
- Qt GUI version:
```
python bal_wallet_utils_qt.py
```

### Building a Windows executable with PyInstaller
From the project root (with the Electrum environment active), you can build the Qt executable using PyInstaller. Example command (adjust the paths if your environment path differs):
```
pyinstaller.exe --onefile --noconsole --add-data "electrum\currencies.json;electrum" --add-data "electrum\bip39_wallet_formats.json;electrum" --add-data "electrum\lnwire\peer_wire.csv;electrum\lnwire" --add-data "electrum\lnwire\onion_wire.csv;electrum\lnwire" --add-binary "env/Lib/site-packages\electrum_ecc\libsecp256k1-6.dll;electrum_ecc" bal_wallet_utils_qt.py
```

Notes:
- Run the command from the project root so relative paths resolve correctly.
- On Windows the --add-data and --add-binary arguments use ";" to separate source and destination.
- If electrum expects additional data files or native DLLs, include them with additional --add-data / --add-binary flags.
- For debugging include --onedir first to inspect the created folder before using --onefile.

### Troubleshooting
- If PyInstaller is not found, run it via Python:
```
python -m PyInstaller <same arguments>
```
- If the frozen exe fails because DLLs or JSON files are missing, add those files explicitly with --add-data or --add-binary.
- Test the build on a clean Windows VM to ensure all runtime dependencies are included.

License and attribution: include your preferred license or attribution details here.
