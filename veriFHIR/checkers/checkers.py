from abc import abstractmethod
import os
from dotenv import load_dotenv
from pathlib import Path
import json
import textwrap
from typing import Tuple, Optional, List, Dict, Tuple
import re
from collections import defaultdict

from veriFHIR.ig.fhir_ig import FHIRIG, Artifact
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

    def _format_proof(self, title: str, elements: List, reverse: bool = False) -> Optional[str]: # TO IMPROVE (check)
        if len(elements) == 0:
            return None
        if isinstance(elements[0], tuple):
            temp: Dict = defaultdict(list)
            for elem in elements:
                temp[elem[1].strip()].append(elem[0])
            elements = [(", ".join(vals), key) for key, vals in temp.items()]
        proof_lines: List[str] = [f"{title}: "]
        proof_lines.append("<ul>")
        for elem in elements:
            if isinstance(elem, str):
                proof_lines.append(f"<li>{elem}</li>")
            elif isinstance(elem[1], list):
                proof_lines.append("<li>")
                proof_lines.append(f"{elem[0]}:")
                proof_lines.append("<ul>")
                for sub_elem in elem[1]:
                    proof_lines.append(f"<li>{sub_elem}</li>")
                proof_lines.append("</ul>")
                proof_lines.append("</li>")
            else:
                if reverse:
                    proof_lines.append(f"<li>{elem[1]}: {elem[0]}</li>")
                else:
                    proof_lines.append(f"<li>{elem[0]}: {elem[1]}</li>")
        proof_lines.append("</ul>")
        proof: str = "\n".join(proof_lines)
        return proof
    
    def _normalize_bool(self, value) -> Optional[bool]:
        if value is True:
            return True
        if value is False:
            return False
        if isinstance(value, str):
            v = value.strip().lower()
            if v == "true":
                return True
            if v == "false":
                return False
        return None


class ArtifactsChecker(Checker):
    def __init__(self, ig: FHIRIG):
        domain: str = "Artifacts"
        elements: List[Dict] = [
            {"names": ["text"]},
            {"names": ["publisher", "contact"], "types": ["ImplementationGuide"]},
            {"names": ["description"], "types": ["StructureDefinition"]}
        ]
        super().__init__(ig, domain, elements)

    def check(self):
        checks: List[Check] = []
        artifacts: List[Artifact] = self.get_ig().get_artifacts()
        profiles: List[Artifact] = [a for a in artifacts if a.get_type() == "StructureDefinition"]
        missing_examples = []
        for profile in profiles: # TO IMPROVE (add to elements)
            content: Dict = profile.get_content()
            resource: Optional[str] = content.get("type") # TO IMPROVE (add getter)
            url: Optional[str] = content.get("url")
            examples_resource: List[Artifact] = [a for a in artifacts if a.get_type() == resource]
            value_example: bool = False
            for example in examples_resource:
                example_content: Optional[dict] = example.get_content()
                meta: Optional[dict] = example_content.get("meta") if example_content else None
                example_profiles: Optional[list] = meta.get("profile") if isinstance(meta, dict) else None
                if example_profiles and url in example_profiles:
                    value_example = True
                    break
            if not value_example:
                missing_examples.append(content.get("id"))
        proof_example: Optional[str] = self._format_proof("Missing example for profile(s): ",  missing_examples)
        checks.append(Check(f"Presence of at least one example for each profile: ", value_example, proof_example, self.get_domain()))
        for elem in self.get_elements():
            artifacts_ko: List[Tuple[str, str]] = []
            artifact_types: List[str] = elem.get("types")
            names: List[str] = elem.get("names")
            if artifact_types:
                artifacts_type = [a for a in artifacts if a.get_type() in artifact_types]
            else:
                artifacts_type = artifacts
            value: Optional[bool] = None
            proof: Optional[str] = None
            if not artifacts_type:
                proof = "No artifacts found for this type."
            else:
                for artifact in artifacts_type:
                    artifact_content: Dict = artifact.get_content()
                    missing = [name for name in names if name not in artifact_content]
                    for m in missing:
                        artifacts_ko.append((m, artifact.get_id()))
                value = not bool(artifacts_ko)
                proof = self._format_proof("Missing fields per artifacts", artifacts_ko, True)
            names_label: str = "element" if len(names) == 1 else "elements"
            names_str: str = ", ".join(names)
            types_str: str = f"artifacts of type {', '.join(artifact_types)}" if artifact_types else "all artifacts"
            checks.append(Check(f"Presence of {names_label} {names_str} in {types_str}: ", value, proof, self.get_domain()))
        return checks


class RefsChecker(Checker):
    def __init__(self, ig: FHIRIG):
        domain: str = "Pages and organization"
        elements: List[Tuple[str, str]] = [
            ("qa.html", "the validation results (QA)")
        ]
        super().__init__(ig, domain, elements)

    def check(self):
        checks: List[Check] = []
        if self.get_ig().get_metadata().get_ig_type() == "IGPublisher":
            for ref, ref_desc in self.get_elements():
                refs: List = []
                for page in self.get_ig().get_pages():
                    pages_refs: Dict[str, str] = page.get_links()
                    for page_ref, page_ref_desc in pages_refs.items():
                        if ref in page_ref:
                            refs.append((page.get_name(), f"{page_ref_desc} ({page_ref})"))
                value: bool = False
                proof: Optional[str] = None
                if len(refs) > 0:
                    value = True
                    proof = self._format_proof("Extract per page: ", refs)
                checks.append(Check(f"Presence of at least one reference to {ref_desc}", value, proof, self.get_domain()))
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
        return self._llm_additional
    
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
        elem_ids: Dict[str, str] = {elem.strip().lower().replace(" ", "_"): elem for elem in self.get_elements()}
        results_ko: Dict[str, List[str]] = {elem_id: [] for elem_id in elem_ids}
        for page in self.get_ig().get_pages():
            elem_ids_page = elem_ids.copy()
            page_text = page.get_text()
            if "fhir_version" in elem_ids_page:
                match = re.search(r'based on fhir\s*[0-6]', page_text, re.IGNORECASE)
                if match :
                    del elem_ids_page["fhir_version"]
            select_elements: str =  "\n* ".join(elem_ids_page.keys())
            user_prompt: str = f"\nElements:\n* {select_elements}\nPage content: {page_text}"
            response: Optional[str] = self.get_llm().openai_chat_completion_response(user_prompt)
            response_bool: bool = False
            if response:
                try:
                    response_json = json.loads(response)
                except:
                    continue
                if isinstance(response_json, dict):
                    response_bool = True
                    for elem_id in results_ko.keys():
                        if elem_id in elem_ids_page:
                            bool_value: Optional[bool] = None
                            for raw_key, raw_value in response_json.items():
                                key: str = raw_key.strip().lower().replace(" ", "_")
                                if key == elem_id:
                                    bool_value = self._normalize_bool(raw_value)
                                    break
                            if bool_value is not True:
                                results_ko[elem_id].append(page.get_name())
            if not response_bool:
                print(f"AllPagesChecker: page {page.get_name()} skipped (LLM error response)")
        
        for elem_id, pages_ko in results_ko.items():
            value: bool = True
            proof: Optional[str] = None 
            if len(pages_ko) > 0:
                value = False
                proof = self._format_proof(f"Missing information {elem_ids[elem_id]} in pages", pages_ko)
            checks.append(Check(f"Presence of {elem_ids[elem_id]} in all pages: ", value, proof, self.get_domain()))
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
            if response:
                response_clean: str = response.lower().strip()
                if response_clean in self.get_elements():
                    results[response_clean].append(page.get_name())
        for elem in self.get_elements():
            response_bool: bool = False
            value: bool = False
            proof: str = ""
            pages: List = []
            if elem == "toc":
                if self.get_ig().get_toc_path():
                    response_bool = True
                    value = True
                    proof = f"Page: {self.get_ig().get_toc_path().name}"
            else:
                pages = results[elem]
                if len(pages) == 1:
                    response_bool = True
                    value = True
                    proof = "Page: " + pages[0]
                elif len(pages) > 1:
                    additional_user_prompt: str = f"\nSearched type: {elem}\nProposed page names: {str(pages)}"
                    response_additional: Optional[str] = self.get_llm_additional().openai_chat_completion_response(additional_user_prompt) #type: ignore
                    if response_additional:
                        response_additional_clean: str = response_additional.lower().strip()
                        for page in pages:
                            page_base = page.rsplit(".", 1)[0]
                            if response_additional_clean == page or response_additional_clean == page_base:
                                response_bool = True
                                value = True
                                proof = "Page: " + page
                                break
            if response_bool:
                checks.append(Check(f"Presence of page: {elem}", value, proof, self.get_domain()))
            else:
                print(f"PageTypeChecker: type {elem} skipped (LLM error response)")
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
            ("downloads", "information on how to access downloadable artifacts and resources"), 
            ("examples", "explicit reference within the narrative text to concrete example resources demonstrating how to use the IG in practice (not just a dedicated 'Examples' section)")
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

    def check(self):
        checks: List[Check] = []
        profiles: List[Artifact] = [a for a in self.get_ig().get_artifacts() if a.get_type() == "StructureDefinition"]
        profiles_elements: List[Tuple[str, str]] = [(p.get_id(), f"a reference to the profile {p.get_id()} (not just the resource type)") for p in profiles] # TO IMROVE (profile name + text)
        all_elements: List[Tuple[str, str]] = self.get_elements() + profiles_elements
        results: Dict[str, List] = {elem[0]: [] for elem in all_elements}
        for elements in [self.get_elements(), profiles_elements]:
            for page in self.get_ig().get_pages():
                if page.get_name() not in ["artifacts.html", "toc.html"]: #TO IMPROVE
                    response_bool: bool = False
                    select_elements: str =  "\n* ".join(f"{k}: {v}" for k, v in elements)
                    user_prompt: str = f"\nElements:\n* {select_elements}\nPage content: {page.get_text()}"
                    response: Optional[str] = self.get_llm().openai_chat_completion_response(user_prompt, TextCheckResponses.get_response_format("responses"))
                    if response:
                        try:
                            response_json = json.loads(response)
                        except:
                            continue
                        if "responses" in response_json.keys():
                            response_json = response_json.get("responses")
                        if isinstance(response_json, list):
                            for elem_response in response_json:
                                if all(k in elem_response.keys() for k in ["id", "extract"]):
                                    response_bool = True
                                    id: str = elem_response.get("id")
                                    extract: Optional[str] = elem_response.get("extract")
                                    if extract:
                                        if id in results.keys():
                                            if extract.lower().strip() not in ["none", "null"]:
                                                results[id].append((page.get_name(), extract))
                                        else:
                                            response_bool = False
                    if not response_bool:
                        print(f"TextChecker: page {page.get_name()} skipped (LLM error response)")
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
        value_profiles: bool = True
        proof_profiles: Optional[str] = None
        result_profiles: List = []
        for id, _ in profiles_elements:
            proof_profile: Optional[str] = None
            if len(results[id]) == 0:
                value_profiles = False
                proof_profile = "no reference"
            else:
                proof_profile = "pages " + ", ".join([r[0] for r in results[id]])
            result_profiles.append((id, proof_profile))
        proof_profiles = self._format_proof("Profile references", result_profiles)
        checks.append(Check(f"Presence of a reference to each profile: ", value_profiles, proof_profiles, self.get_domain()))
        return checks