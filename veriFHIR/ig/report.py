from __future__ import annotations
from collections import defaultdict
from tabulate import tabulate # type: ignore[import-untyped]
from bs4 import BeautifulSoup
from pathlib import Path
from jinja2 import Template
from datetime import datetime
from typing import List, DefaultDict, Optional, Union

from veriFHIR.ig.fhir_ig import Metadata


class Check:
    def __init__(self, name: str, value: Optional[bool], proof: Optional[str], domain: str):
        self._name: str = name
        self._value: Optional[bool] = value
        self._proof: Optional[str] = proof
        self._domain: str = domain

    def get_name(self) -> str:
        return self._name
    def get_value(self) -> Optional[bool]:
        return self._value
    def get_proof(self) -> Optional[str]:
        return self._proof
    def get_domain(self) -> str:
        return self._domain

class Report:
    def __init__(self):
        self._checks: List[Check] = []

    def get_checks(self) -> List[Check]:
        return self._checks

    def add_checks(self, checks: List[Check]):
        self._checks.extend(checks)

    def _count_values(self) -> defaultdict:
        domain_counts: DefaultDict[str, dict[str, int]] = defaultdict(lambda: {"True": 0, "False": 0})
        for check in self.get_checks():
            if check.get_value():
                domain_counts[check.get_domain()]["True"] += 1
            elif check.get_value() == False:
                domain_counts[check.get_domain()]["False"] += 1
        return domain_counts

    def write(self, output_path: Path, ig_metadata: Metadata):
        criteria_summary: defaultdict = self._count_values()
        summary_table_rows: List[List] = []
        for domain, counts in criteria_summary.items():
            true_count: int = counts["True"]
            false_count: int = counts["False"]
            total: int = true_count + false_count
            true_pct: int = 0
            false_pct: int = 0
            if total != 0:
                true_pct = int(true_count / total * 100)
                false_pct = int(false_count / total * 100)
            bar_html: str = f"""
            <div style="display:flex; width:150px; border:1px solid #ccc; border-radius:4px; overflow:hidden;">
                <div style="background-color:green; width:{true_pct}%; color:white; text-align:center;">{true_count}</div>
                <div style="background-color:red; width:{false_pct}%; color:white; text-align:center;">{false_count}</div>
            </div>
            """
            summary_table_rows.append([domain, bar_html])
        summary_table: str = tabulate(summary_table_rows, tablefmt="html", headers=["Domain", "Checks (✅/❌)"])
        summary_table_soup: BeautifulSoup = BeautifulSoup(summary_table, "html.parser")
        for i, sum_row in enumerate(summary_table_rows):
            tr = summary_table_soup.find_all("tr")[i+1]
            td_bar = tr.find_all("td")[1]
            td_bar.clear()
            td_bar.append(BeautifulSoup(sum_row[1], "html.parser"))
            tr["class"] = "summary-row"
        if summary_table_soup.table:
            summary_table_soup.table["class"] = "grid"
        checks_dicts: List[dict] = [{"Domain": check.get_domain(), "Criteria": check.get_name(), "Check": check.get_value(), "Proof": check.get_proof()} for check in self.get_checks()]
        checks_table: str = tabulate(checks_dicts, tablefmt="html", headers="keys")
        checks_table = checks_table.replace("&lt;", "<").replace("&gt;", ">")
        checks_table_soup: BeautifulSoup = BeautifulSoup(checks_table, "html.parser")
        for row in checks_table_soup.find_all("tr")[1:]:
            value_td = row.find_all("td")[2]
            if "True" in value_td.text:
                value_td.string = "✅"
                row["class"] = "true-check"
            elif "False" in value_td.text:
                value_td.string = "❌"
                row["class"] = "false-check"
            value_td["class"] = "check-cell"
        if checks_table_soup.table:
            checks_table_soup.table["class"] = "grid"
        css_path: Path = Path("veriFHIR", "config", "report.css")
        with open(css_path, "r", encoding="utf-8") as css_file:
            css_content: str = css_file.read()
        template_str: str = """
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
        <head>
            <meta charset="utf-8">
            <title>Quality review report</title>
            <style>{{ css }}</style>
        </head>
        <body>
            <h1>Quality review summary</h1>
            <p>Generated {{ date }}, FHIR version {{ fhir_version }} for {{ name }}#{{ version }}</p>
            {{ summary_table | safe }}
            <h1 id="quality">Quality checks</h1>
            <p>Inspired by IG Best Practices</a>
            described in <a href="https://build.fhir.org/ig/FHIR/ig-guidance/best-practice.html">Guidance for FHIR IG Creation</a>
            and <a href="https://confluence.hl7.org/spaces/FHIR/pages/66930646/FHIR+Implementation+Guide+Publishing+Requirements">FHIR IG Publishing requirements</a></p>
            {{ criteria_table | safe }}
        </body>
        </html>
        """
        template: Template = Template(template_str)
        now: datetime = datetime.now()
        html_rendered: str = template.render(
            css = css_content,
            date = now.strftime("%A %d %B %Y (%H:%M)"),
            fhir_version = ig_metadata.get_fhir_version(),
            name = ig_metadata.get_name(),
            version = ig_metadata.get_version(),
            criteria_table = str(checks_table_soup),
            summary_table = str(summary_table_soup)
        )
        output_file: Path= Path(output_path, f"quality-review_{ig_metadata.get_name()}_{now.strftime('%Y-%m-%d-%H-%M')}.html")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_rendered)
        return output_file
