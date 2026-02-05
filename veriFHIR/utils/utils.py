import zipfile
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import Tuple


def extract_zip(zip_path: str) -> Tuple[TemporaryDirectory, Path]:
    temp_dir: TemporaryDirectory = TemporaryDirectory()
    temp_path: Path = Path(temp_dir.name)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_path)
    return temp_dir, temp_path