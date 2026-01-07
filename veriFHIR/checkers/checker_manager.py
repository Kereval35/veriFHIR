from typing import List
from pathlib import Path

from veriFHIR.checkers.checkers import Checker
from veriFHIR.ig.report import Report, Check


class CheckerManager:
    def __init__(self):
        self.checkers: List[Checker] = []
        
    def register(self, checker: Checker):
        self.checkers.append(checker)

    def check(self) -> Report:
        report: Report = Report()
        for checker in self.checkers:
            checks: List[Check] = checker.check()
            report.add_checks(checks)
        return report