from abc import abstractmethod
import os
from dotenv import load_dotenv
from pathlib import Path
import json
import textwrap
from typing import Tuple, Optional, List, Dict, Tuple
import re
from collections import defaultdict
from itertools import combinations

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

    def _format_proof(self, title: str, elements: List, reverse: bool = False) -> Optional[str]:
        if len(elements) == 0:
            return None
        if isinstance(elements[0], tuple) and not isinstance(elements[0][1], list):
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
            v: str = value.strip().lower()
            if v == "true":
                return True
            if v == "false":
                return False
        return None


class ArtifactsChecker(Checker):
    def __init__(self, ig: FHIRIG, check_format: bool = False, check_examples: bool = True):
        domain: str = "Artifacts"
        elements: List[Dict[str, List[str]]] = [
            {"names": ["id", "text"]},
            {"names": ["publisher", "contact"], "types": ["ImplementationGuide"]},
            {"names": ["description"], "types": ["StructureDefinition"]}
        ]
        super().__init__(ig, domain, elements)
        self._check_format : bool = check_format
        self._check_examples : bool = check_examples

    def check(self):
        checks: List[Check] = []
        artifacts: List[Artifact] = self.get_ig().get_artifacts()

        for elem in self.get_elements():
            artifacts_ko: List[Tuple[str, str]] = []
            artifact_types: List[str] = elem.get("types")
            names: List[str] = elem.get("names")
            if artifact_types:
                artifacts_type = [a for a in artifacts if a.get_resource_type() in artifact_types]
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

        if self._check_examples:
            missing_examples: List = []
            profiles: List[Artifact] = [artifact for artifact in self.get_ig().get_artifacts_type("StructureDefinition") if artifact.get_content().get("kind") == "resource"]
            for profile in profiles:
                content: Dict = profile.get_content()
                resource: Optional[str] = content.get("type")
                url: Optional[str] = content.get("url")
                if resource:
                    examples_resource: List[Artifact] = self.get_ig().get_artifacts_type(resource)
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
            proof_examples: Optional[str] = None
            value_examples: bool = True
            if len(missing_examples) > 0:
                value_examples = False
                proof_examples = self._format_proof("Missing example for profile(s): ",  missing_examples)
            checks.append(Check(f"Presence of at least one example for each profile: ", value_examples, proof_examples, self.get_domain()))

        if self._check_format:
            formats: Dict[str, Dict[str, str]] = {
                "id": {"regex": r'^[a-z0-9]+(-[a-z0-9]+)*$', "name": "kebab-case"},
                "name": {"regex": r'^(?=[A-Z])(?=(?:.*[A-Z]){2,})(?=.*[a-z])[A-Za-z0-9]+$', "name": "PascalCase"},
                "title": {"regex": r'^[a-zA-Z0-9 ]+$', "name": "alphanumeric + space only"},
                "MATCH": {}
                }
            format_results: Dict[str, List] = {format: [] for format in formats.keys()}
            for artifact in artifacts:
                artifact_content = artifact.get_content()
                artifact_match: Dict[str, Optional[str]] = {f: None for f in formats.keys()}
                for element, format in formats.items():
                    if format:
                        artifact_element: Optional[str] = artifact_content.get(element)
                        if artifact_element and isinstance(artifact_element, str):
                            if not bool(re.fullmatch(format["regex"], artifact_element)):
                                result_str: str = artifact_element
                                if element != "id":
                                    result_str += f" (id: {artifact.get_id()})"
                                format_results[element].append(result_str)
                            else:
                                artifact_match[element] = artifact_element.lower().replace("-", "").replace(" ", "")
                if "MATCH" in formats.keys():
                    mismatch: List[Tuple[str, str]] = []
                    for k1, k2 in combinations(artifact_match.keys(), 2):
                        if artifact_match[k1] and artifact_match[k2]:
                            if artifact_match[k1] != artifact_match[k2]:
                                mismatch.append((k1, k2))
                    if len(mismatch) > 0:
                        element_values: str = ", ".join(f"{m}: {artifact_content.get(m)}" for m in formats.keys() if m != "MATCH")
                        mismatch_values: str = ", ".join(f"{m[0]}/{m[1]}" for m in mismatch)
                        format_results["MATCH"].append(f"{element_values} ({mismatch_values})")
            for element, result in format_results.items():
                value_format: bool = True
                proof_format: Optional[str] = None
                title: str = "Artifacts id-name/title match:" if element == "MATCH" else f"Artifact {element} in {formats[element]['name']} format: "
                proof_title: str = "Artifacts with mismatches" if element == "MATCH" else f"Artifacts with invalid {element} format"
                if len(result) > 0:
                    value_format = False
                    proof_format = self._format_proof(proof_title, result)
                checks.append(Check(title, value_format, proof_format, self.get_domain())) 

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
                            refs.append((page.get_name(), f"\"{page_ref_desc}\" ({page_ref})"))
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
            - Do not include additional explanations, comments, or Markdown formatting.
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
    def __init__(self, ig: FHIRIG, model: str, check_references: bool = True):
        domain: str = "Writing and narrative"
        elements: List[Tuple[str, str]] = [
            ("prior", "a section that explains key information that needs to be understood prior to reading the IG"),
            ("ms", "an explanation of what 'mustSupport' means for different types of implementations of the IG"),
            ("community", "information on how to engage with the community"),
            ("relationship", "an explanation of the relationship of the IG to any other guides"),
            ("registry", "a reference to the IG registry as a location to find more IGs of interest"),
            ("background", "background information providing context and motivation for the IG"),
            ("downloads", "information on how to access downloadable artifacts and resources"), 
            ("resources_examples", "explicit reference within the narrative text to concrete FHIR example resources demonstrating how to use the IG in practice (not just a dedicated 'Examples' section)"),
            ("queries_examples", "concrete example queries that illustrate how to interact with or search for resources related to the IG, when applicable")
        ]
        super().__init__(ig, domain, elements, model)
        self._check_references: bool = check_references

    def _set_llm(self):
        system_prompt: str = """
        Given the content of a FHIR Implementation Guide page and a list of elements (each with a unique `id` and a `description`), identify for each element whether it appears in the page.
        - If the element appears, return a short excerpt showing where and how the element appears in the page.
        - If it does not appear, return `null`.

        **Output format:** For each element, produce an object containing the element id (`id`) and the excerpt string, if found, or null (`extract`). The output must be a single valid JSON object with a field `responses` containing an array of such objects.
        Return a JSON object:
        {"responses": [...]}
        Each object contains:
        - `id`: element id
        - `extract`: exact text excerpt if found (verbatim), or null

        **Constraints:**
        - Output only valid JSON.
        - The excerpt must be taken directly from the page text without any modifications, paraphrasing, or additions.
        """ 
        llm: GPT = GPT(textwrap.dedent(system_prompt), self.get_api_key(), self.get_model())
        return (llm, None)

    def check(self):
        checks: List[Check] = []
        all_elements: List = [self.get_elements()]

        if self._check_references:
            profiles: List[Artifact] = [artifact for artifact in self.get_ig().get_artifacts_type("StructureDefinition") if artifact.get_content().get("kind") == "resource"]
            profiles_str: List[Tuple] = []
            for profile in profiles:
                profile_name = profile.get_content().get("name")
                if profile_name:
                    profiles_str.append((profile.get_id(), profile_name))
                else:
                    profiles_str.append((profile.get_id(), profile.get_id()))
            profiles_elements: List[Tuple[str, str]] = [(p[0], f"a reference to the profile {p[1]} (not just the resource type)") for p in profiles_str]
            sps: List[Artifact] = self.get_ig().get_artifacts_type("SearchParameter")
            sps_str: List[Tuple] = []
            for sp in sps:
                sp_name = sp.get_content().get("name")
                if sp_name:
                    sps_str.append((sp.get_id(), sp_name))
                else:
                    sps_str.append((sp.get_id(), sp.get_id()))
            sps_elements: List[Tuple[str, str]] = [(s[0], f"a reference to the search parameter {s[1]}") for s in sps_str]
            all_elements.extend([profiles_elements, sps_elements])

        all_elements_flat: List[Tuple[str, str]] = [e for sub_elements in all_elements for e in sub_elements]
        results: Dict[str, List] = {elem[0]: [] for elem in all_elements_flat}
        for elements in all_elements:
            if len(elements) > 0:
                for page in self.get_ig().get_pages():
                    if page.get_name() not in ["artifacts.html", "toc.html"]:
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
                                                    results[id].append((page.get_name(), f"\"{extract}\""))
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

        for name, artifacts_elements in {"profile": profiles_elements, "search parameter": sps_elements}.items():
            value_artifacts: Optional[bool] = True
            proof_artifacts: Optional[str] = None
            if len(artifacts_elements) == 0:
                value_artifacts = None
                proof_artifacts = f"No artifact of type {name}"
            else:
                result_artifacts: List = []
                for id, _ in artifacts_elements:
                    proof_artifact: Optional[str] = None
                    if len(results[id]) == 0:
                        value_artifacts = False
                        proof_artifact = "no reference"
                    else:
                        proof_artifact = "pages " + ", ".join([r[0] for r in results[id]])
                    result_artifacts.append((id, proof_artifact))
                proof_artifacts = self._format_proof(f"{name.capitalize()} references", result_artifacts)
            checks.append(Check(f"Presence of a reference to each {name}: ", value_artifacts, proof_artifacts, self.get_domain()))
        return checks
    

class AmbiguousWordingChecker(LLMChecker):
    def __init__(self, ig: FHIRIG, model: str):
        domain: str = "Writing and narrative"
        elements: List = []
        super().__init__(ig, domain, elements, model) 

    def _set_llm(self):
        system_prompt: str = """
        Given the content of a FHIR Implementation Guide page, identify ONLY high-confidence technical ambiguities that would likely lead to incorrect implementation.
        - Evaluate statements in the context of the entire page.
        - Consider ONLY ambiguities that would force an implementer to make an uncertain or conflicting technical decision.
        ### IMPORTANT:
        Ignore isolated labels, headings, or short fragments unless they explicitly express a constraint or implementation rule. 
        ### EXCLUDE COMPLETELY:
        - vague wording without implementation consequences
        - editorial or explanatory ambiguity
        - unclear but non-actionable statements
        - anything resolvable by reading the rest of the section
        - structural or formatting issues
        - fragments, headings, labels, identifiers, or metadata

        **Output format:**  
        Return a JSON object:
        {"responses": [...]}
        Each object contains:
        - `extract`: exact text excerpt (verbatim)
        - `reason`: why this creates a concrete implementation conflict
        If nothing meets ALL criteria:
        {"responses": []}

        **Constraints:**
        - Output only valid JSON.
        - The excerpt must be taken directly from the page text without any modifications, paraphrasing, or additions.
        - Only return validated, high-impact technical ambiguities
        """
        llm: GPT = GPT(textwrap.dedent(system_prompt), self.get_api_key(), self.get_model())
        return (llm, None)
    
    def check(self):
        results: List[Tuple[str, str]] = []
        value: Optional[bool] = None
        proof: Optional[str] = None
        for page in self.get_ig().get_pages():
            page_name = page.get_name()
            user_prompt: str = f"Page content: {page.get_text()}"
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
                        if all(k in elem_response.keys() for k in ["extract", "reason"]):
                            results.append((page_name, f"\"{elem_response['extract']}\" ➡️ {elem_response['reason']}"))
        if len(results) > 0:
            value = False
            temp = defaultdict(list)
            for k, v in results:
                temp[k].append(v)
            proof = self._format_proof("Ambiguous or unclear technical formulations", list(temp.items()))
        else:
            value = True
            proof = "No ambiguous or unclear technical formulations."
        checks: List[Check] = [Check(f"Clarity for technical implementation: ", value, proof, self.get_domain())]
        return checks