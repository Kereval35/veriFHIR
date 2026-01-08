from __future__ import annotations
from pathlib import Path
import json
import codecs
import tarfile
from bs4 import BeautifulSoup
from typing import List


class Metadata:
    def __init__(self, IG: FHIRIG):
        self._load_metadata(IG)

    def _set_ig_type(self, ig_type: str):
        self._ig_type: str = ig_type
    def _set_fhir_version(self, fhir_version: str):
        self._fhir_version: str = fhir_version
    def _set_name(self, name: str):
        self._name: str = name
    def _set_version(self, version: str):
        self._version: str = version

    def get_ig_type(self) -> str:
        return self._ig_type
    def get_fhir_version(self) -> str:
        return self._fhir_version
    def get_name(self) -> str:
        return self._name
    def get_version(self) -> str:
        return self._version

    def _load_metadata(self, IG: FHIRIG):
        file_path: Path
        contents: dict
        if Path(IG.get_path(), "site").exists():
            self._set_ig_type("IGPublisher")
            file_path = Path(IG.get_path(), "site", "package.manifest.json")
            contents = json.load(codecs.open(str(file_path), 'r', 'utf-8-sig'))
            self._set_fhir_version(contents['fhirVersion'][0])
            IG.set_path(Path(IG.get_path(), "site"))
        else:
            self._set_ig_type("Simplifier")
            package_path: Path = Path(IG.get_path(), "packages")
            package_zip: Path = next(Path(package_path).iterdir())
            with tarfile.open(Path(package_path, package_zip), "r:gz") as tar_ref:
                tar_ref.extractall(package_path)
            file_path = Path(package_path, 'package', 'package.json')
            contents = json.load(codecs.open(str(file_path), 'r', 'utf-8-sig'))
            self._set_fhir_version(contents['fhir-version-list'][0])
        self._set_name(contents["name"])
        self._set_version(contents["version"])


class Artifact:
    def __init__(self, id: str, type: str, path: Path):
        self._id: str = id
        self._type: str = type
        self._path: Path = path

    def get_id(self) -> str:
        return self._id
    def get_type(self) -> str:
        return self._type
    def get_path(self) -> Path:
        return self._path
    
    def get_content(self) -> dict:
        content = json.load(codecs.open(str(self.get_path()), 'r', 'utf-8-sig'))
        return content

    def get_mustSupport_elements(self) -> List[str]:
        content: dict = self.get_content()
        if content.get("resourceType") != "StructureDefinition":
            return []
        results: List[str] = []
        for elements in (
            (content.get("snapshot", {}).get("element", [])),
            (content.get("differential", {}).get("element", [])),
        ):
            for el in elements:
                if el.get("mustSupport") is True:
                    results.append(el.get("path"))
        return results


class Page:
    def __init__(self, path: Path, name: str):
        self._path: Path = path
        self._name: str = name
        self._text: str = self._parse_page()

    def get_path(self) -> Path:
        return self._path
    def get_name(self) -> str:
        return self._name
    def get_text(self) -> str:
        return self._text

    def _parse_page(self) -> str:
        with open(Path(self.get_path()), 'r', encoding="utf8") as f:
            contents: str = f.read()
        soup: BeautifulSoup = BeautifulSoup(contents, 'html.parser')
        return soup.get_text()


class FHIRIG():
    def __init__(self, ig_path: Path):
        self._path: Path = ig_path
        self._metadata: Metadata = Metadata(self)
        self._toc_path: Path = self._find_toc_path()
        self._pages: List[Page] = self._load_pages()
        self._artifacts: List[Artifact] = self._load_artifacts()
        self._mustSupport: bool = self._check_mustSupport()

    def set_path(self, path: Path):
        self._path = path

    def get_path(self) -> Path:
        return self._path
    def get_metadata(self) -> Metadata:
        return self._metadata
    def get_toc_path(self) -> Path:
        return self._toc_path
    def get_pages(self) -> List[Page]:
        return self._pages
    def get_artifacts(self) -> List[Artifact]:
        return self._artifacts
    def get_artifacts_type(self, type: str) -> List[Artifact]:
        return [artifact for artifact in self.get_artifacts() if artifact.get_type() == type]
    def get_mustSupport(self) -> bool:
        return self._mustSupport

    def _find_toc_path(self) -> Path:
        toc_path: Path
        if self.get_metadata().get_ig_type() == "IGPublisher":
            toc_path = Path(self.get_path(), "toc.html")
        else:
            toc_path = Path(self.get_path(), "Home.html")
        if toc_path.exists():
            return toc_path
        else:
            raise Exception("IG itoc page not found.")
        
    def _load_pages(self) -> List[Page]:
        pages: List[Page] = []
        with open(self.get_toc_path(), 'r' ,encoding="utf8") as f:
            contents: str = f.read()
        soup: BeautifulSoup = BeautifulSoup(contents, "html.parser")
        for a in soup.find_all("a", href=True):
            link = a["href"]
            add: bool = True
            if isinstance(link, str) and link.endswith(".html"):
                if Path(self.get_path(), link).exists():
                    if self.get_metadata().get_ig_type() == "IGPublisher":
                        if Path(self.get_path(), link.replace(".html", ".json")).exists():
                            add = False
                    else:
                        if "artifact" in link.lower():
                            add = False
                    if add and link not in [page.get_name() for page in pages]:
                        pages.append(Page(Path(self.get_path(), link), link))
        if len(pages) == 0:
            raise Exception("No pages found from the IG index page.")
        if len(pages) > 50:
            raise Exception(f"Too many narrative pages ({len(pages)}) in the IG.") 
        return pages
    

    def _load_artifacts(self) -> List[Artifact]:
        artifacts: List[Artifact] = []
        if self.get_metadata().get_ig_type() == "IGPublisher":
            canonicals_path: Path = Path(self.get_path(), "canonicals.json")
            canonicals = []
            if canonicals_path.is_file():
                content = json.load(codecs.open(str(canonicals_path), 'r', 'utf-8-sig'))
                if isinstance(content, List):
                    for artifact in content:
                        canonicals.append(artifact["id"])
            for file in self.get_path().glob("*.json"):
                content = json.load(codecs.open(str(file), 'r', 'utf-8-sig'))
                if isinstance(content, dict) and ("id" in artifact.keys() and "resourceType" in content.keys()) and content["id"] in canonicals:
                    artifacts.append(Artifact(content["id"], content["resourceType"], file))
        else:
            artifacts_path: Path = Path(self.get_path(), "artifacts")
            if artifacts_path.exists():
                for file in artifacts_path.glob("*.json"):
                    content = json.load(codecs.open(str(file), 'r', 'utf-8-sig'))
                    if isinstance(content, dict) and ("id" in content.keys() and "resourceType" in content.keys()):
                        artifacts.append(Artifact(content["id"], content["resourceType"], file))
        return artifacts
    
    def _check_mustSupport(self) -> bool:
        mustSupport: bool = False
        for artifact in self.get_artifacts():
            mustSupport_elements: List[str] = artifact.get_mustSupport_elements()
            if len(mustSupport_elements) > 0:
                mustSupport = True
                break
        return mustSupport