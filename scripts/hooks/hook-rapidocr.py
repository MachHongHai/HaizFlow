"""RapidOCR requires config/dictionaries at import, never bundled model weights."""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("rapidocr", includes=["**/*.yaml", "**/*.yml", "**/*.txt"])
