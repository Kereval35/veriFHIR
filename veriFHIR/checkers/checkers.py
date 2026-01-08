from abc import abstractmethod
import os
from dotenv import load_dotenv
from pathlib import Path
import json
import textwrap
from typing import Tuple, Optional, List, Dict, Tuple

from veriFHIR.ig.fhir_ig import FHIRIG
from veriFHIR.ig.report import Check
from veriFHIR.llm.gpt import GPT
from veriFHIR.llm.response_formats import TextCheckResponses


class Checker:
    def __init__(self, ig: FHIRIG, domain: str, elements: List):
        self._ig: FHIRIG = ig
        self._domain: str = domain
        self._elements: List = elements

    def get_ig(self) -> FHIRIG:
        return self._ig
    def get_domain(self) -> str:
        return self._domain
    def get_elements(self) -> List:
        return self._elements

    @abstractmethod
    def check(self) -> List[Check]:
        pass

    def _format_proof(self, title: str, elements: List) -> Optional[str]:
        if len(elements) == 0:
            return None
        proof_lines: List[str] = [f"{title}: "]
        proof_lines.append("<ul>")
        for elem in elements:
            if isinstance(elem, str):
                proof_lines.append(f"<li>{elem}</li>")
            elif isinstance(elem[1], List):
                proof_lines.append("<li>")
                proof_lines.append(f"{elem[0]}:")
                proof_lines.append("<ul>")
                for sub_elem in elem[1]:
                    proof_lines.append(f"<li>{sub_elem}</li>")
                proof_lines.append("</ul>")
                proof_lines.append("</li>")
            else:
                proof_lines.append(f"<li>{elem[0]}: {elem[1]}</li>")
        proof_lines.append("</ul>")
        proof: str = "\n".join(proof_lines)
        return proof


class ArtifactsChecker(Checker):
    def __init__(self, ig: FHIRIG):
        domain: str = "Artifacts"
        elements: List[Dict] = [
            {"names": ["text"]},
            {"names": ["publisher", "contact"], "types": ["ImplementationGuide"]}
        ]
        super().__init__(ig, domain, elements)

    """
    def _format_proof(self, artifacts_ko: dict) -> Optional[str]:
        if not artifacts_ko:
            return None
        proof_lines: List[str] = ["<ul>"]
        for artifact_id, missing in artifacts_ko.items():
            proof_lines.append(f"<li><b>Artifact (id): {artifact_id}</b>")
            proof_lines.append("<ul>")
            for field in missing:
                proof_lines.append(f"<li>Missing field: {field}</li>")
            proof_lines.append("</ul></li>")
        proof_lines.append("</ul>")
        proof = "\n".join(proof_lines)
        return proof
    """

    def check(self):
        checks: List[Check] = []
        for elem in self.get_elements():
            artifacts_ko: List[Tuple[str, List[str]]] = []
            artifact_types: List[str] = elem.get("types")
            for artifact in self.get_ig().get_artifacts():
                artifact_content: Dict = artifact.get_content()
                if artifact_types and artifact_content.get("resourceType") not in artifact_types:
                    continue
                missing: List[str] = []
                names: List[str] = elem.get("names")
                for name in names:
                    if name not in artifact_content:
                        missing.append(name)
                if len(missing) > 0:
                    artifacts_ko.append((artifact.get_id(), missing))
            value: bool = not bool(artifacts_ko)
            proof: Optional[str] = self._format_proof("Missing fields per artifacts", artifacts_ko)
            names_label: str = "element" if len(names) == 1 else "elements"
            names_str: str = ", ".join(names)
            types_str: str = f"artifacts of type {', '.join(artifact_types)}" if artifact_types else "all artifacts"
            checks.append(Check(f"Presence of {names_label} {names_str} in {types_str}: ", value, proof, self.get_domain()))
        return checks


class LLMChecker(Checker):
    def __init__(self, ig: FHIRIG, domain: str, elements: List, model: str):
        super().__init__(ig, domain, elements) 
        load_dotenv(dotenv_path=Path("veriFHIR", "config", ".env"))
        if os.getenv("OPENAI_API_KEY") is None:
            raise Exception("OpenAI API key not found.")
        self._api_key: str = os.getenv("OPENAI_API_KEY") #type: ignore
        self._model: str = model
        self._llm: GPT
        self._llm_additional: Optional[GPT]
        self._llm, self._llm_additional = self._set_llm()

    def get_api_key(self) -> str:
        return self._api_key
    def get_model(self) -> str:
        return self._model
    def get_llm(self) -> GPT:
        return self._llm
    def get_llm_additional(self) -> Optional[GPT]:
        return self._llm
    
    @abstractmethod
    def _set_llm(self) -> Tuple[GPT, Optional[GPT]]:
        pass


class AllPagesChecker(LLMChecker):
    def __init__(self, ig: FHIRIG, model: str):
        domain: str = "Pages and organization"
        elements: List[str] = ["FHIR version", "IG version"]
        super().__init__(ig, domain, elements, model) 

    def _set_llm(self):
        system_prompt: str = """
        Given the content of a FHIR Implementation Guide page and a list of information, identify for each piece of information whether it appears in the page.
            - If the information appears, return true.
            - If it does not appear, return false.
        **Output format:** Produce a single valid JSON object where each key is the exact information label and each value is either true or false.
        **Constraints:**
            - Do not include explanations, comments, or Markdown formatting.
            - Output only valid JSON.
        """      
        llm: GPT = GPT(system_prompt, self.get_api_key(), self.get_model())
        return (llm, None)
    
    def check(self):
        checks: List[Check] = []
        results_ko: Dict[str, List] = {elem: [] for elem in self.get_elements()}
        for page in self.get_ig().get_pages():
            for i in range(0, len(self.get_elements()), 5):
                select_elements: str =  "\n* ".join(self.get_elements()[i:i+5])
                user_prompt: str = f"\nElements:\n* {select_elements}\nPage content: {page.get_text()}"
                response: Optional[str] = self.get_llm().openai_chat_completion_response(user_prompt)
                if response:
                    response_json = json.loads(response)
                    if isinstance(response_json, dict):
                        for elem, present in response_json.items():
                            if present == False:
                                if elem in results_ko.keys():
                                    results_ko[elem].append(page.get_name())
        for elem, pages_ko in results_ko.items():
            value: bool = True
            proof: Optional[str] = None 
            if len(pages_ko) > 0:
                value = False
                proof = self._format_proof(f"Missing information {elem} in pages", pages_ko)
                #proof = f"Missing information {elem} in pages: {', '.join(pages_ko)}"
            checks.append(Check(f"Presence of {elem} in all pages: ", value, proof, self.get_domain()))
        return checks


class PageTypeChecker(LLMChecker):
    def __init__(self, ig: FHIRIG, model: str):
        domain: str = "Pages and organization"
        elements: List[str] = ["index", "toc", "artifacts"]
        super().__init__(ig, domain, elements, model) 

    def _set_llm(self):
        base_prompt: str = "Given the name and content of a FHIR implementation guide page, determine which type it matches. Return only one type or None if it does not match any."
        system_prompt: str = f"{base_prompt}\nPage types: {', '.join(e for e in self.get_elements() if e != 'toc')}"     
        llm: GPT = GPT(system_prompt, self.get_api_key(), self.get_model())
        additional_system_prompt: str = "Which of the following page names best matches the given type? Return only the exact page name." 
        llm_additional: GPT = GPT(additional_system_prompt, self.get_api_key(), self.get_model())
        return (llm, llm_additional)

    def check(self):
        checks: List[Check] = []
        results: Dict[str, List] = {elem: [] for elem in self.get_elements()}
        for page in self.get_ig().get_pages():
            user_prompt: str = f"\nPage name: {page.get_name()}\nPage content:\n{page.get_text()}"
            response: Optional[str] = self.get_llm().openai_chat_completion_response(user_prompt)
            if response and response.lower().strip() in self.get_elements():
                results[response].append(page.get_name())
        for elem in self.get_elements():
            value: bool = False
            proof: str = ""
            pages: List = []
            if elem == "toc":
                if self.get_ig().get_toc_path():
                    value = True
                    proof = self.get_ig().get_toc_path().name
            else:
                pages = results[elem]
                if len(pages) == 1:
                    value = True
                    proof = "Page: " + pages[0]
                elif len(pages) > 1:
                    additional_user_prompt: str = f"\nType: {elem}\nPage names: {str(pages)}"
                    if self.get_llm_additional():
                        response_additional: Optional[str] = self.get_llm_additional().openai_chat_completion_response(additional_user_prompt) #type: ignore
                    else:
                        raise Exception("Missing additional LLM.")
                    if response_additional:
                        response_clean: str = response_additional.lower().strip()
                        for page in pages:
                            page_base = page.rsplit(".", 1)[0]
                            if response_clean == page or response_clean == page_base:
                                value = True
                                proof = "Page: " + page
                                break
                    else:
                        raise Exception("Empty response from LLM.")
            checks.append(Check(f"Presence of page: {elem}", value, proof, self.get_domain()))
        return checks


class TextChecker(LLMChecker):
    def __init__(self, ig: FHIRIG, model: str):
        domain: str = "Writing and narrative"
        elements: List[Tuple[str, str]] = [
            ("prior", "a section that explains key information that needs to be understood prior to reading the IG"),
            ("ms", "an explanation of what 'mustSupport' means for different types of implementations of the IG"),
            ("community", "information on how to engage with the community"),
            ("relationship", "an explanation of the relationship of the IG to any other guides"),
            ("registry", "a reference to the IG registry as a location to find more IGs of interest"),
            ("background", "background information providing context and motivation for the IG"),
            ("downloads", "information on how to access downloadable artifacts and resources")
        ]
        super().__init__(ig, domain, elements, model) 

    def _set_llm(self):
        system_prompt: str = """
        Given the content of a FHIR Implementation Guide page and a list of elements (each with a unique `id` and a `description`), identify for each element whether it appears in the page.
            - If the element appears, return a short excerpt showing where and how the element appears in the page.
            - If it does not appear, return `null`.
        **Output format:** For each element, produce an object containing the element id (`id`) and the excerpt string, if found, or null (`extract`). The output must be a single valid JSON object with a field `responses` containing an array of such objects.
        **Constraints:**
            - The excerpt must be taken directly from the page text without any modifications, paraphrasing, or additions.
            - Do not include explanations, comments, or Markdown formatting.
            - Output only valid JSON.
        """ 
        llm: GPT = GPT(textwrap.dedent(system_prompt), self.get_api_key(), self.get_model())
        return (llm, None)
    
    """
    def _format_proof(self, result: list[dict]) -> Optional[str]:
        if not result:
            return None
        lines: List[str] = ["<ul>"]
        for item in result:
            lines.append(f"  <li>Extract (page {item['page']}): {item['extract']}</li>")
        lines.append("</ul>")
        return "\n".join(lines)
    """

    def check(self):
        checks: List[Check] = []
        results: Dict[str, List] = {elem[0]: [] for elem in self.get_elements()}
        for page in self.get_ig().get_pages():
            for i in range(0, len(self.get_elements()), 5):
                select_elements: str =  "\n* ".join(f"{k}: {v}" for k, v in self.get_elements()[i:i+5])
                user_prompt: str = f"\nElements:\n* {select_elements}\nPage content: {page.get_text()}"
                response: Optional[str] = self.get_llm().openai_chat_completion_response(user_prompt, TextCheckResponses.get_response_format("reponses"))
                if response:
                    response_json = json.loads(response)
                    if "responses" in response_json.keys():
                        response_json = response_json.get("responses")
                    if isinstance(response_json, list):
                        for elem_response in response_json:
                            if all(k in elem_response.keys() for k in ["id", "extract"]):
                                id: str = elem_response.get("id")
                                extract: Optional[str] = elem_response.get("extract")
                                if extract:
                                    if id in results.keys() and extract.lower() not in ["none", "null"]:
                                        results[id].append((page.get_name(), extract))
        for id, elem in self.get_elements():
            value: Optional[bool] = None
            proof: Optional[str] = None
            result: List = [r for r in results[id] if r[1]]
            if id == "ms" and not self.get_ig().get_mustSupport():
                proof = "mustSupport not used."
            elif bool(result):
                value = True
                proof = self._format_proof("Extract per page", result)
            else:
                value = False
            checks.append(Check(f"Presence of {elem}: ", value, proof, self.get_domain()))
        return checks