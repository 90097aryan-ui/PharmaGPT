"""
review/review_models.py — Data models for the Validation Review Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Severity(str, Enum):
    CRITICAL    = "Critical"
    MAJOR       = "Major"
    MINOR       = "Minor"
    OBSERVATION = "Observation"


class ReadinessLevel(str, Enum):
    READY     = "Ready for QA"
    MINOR     = "Needs Minor Review"
    MAJOR     = "Needs Major Revision"
    NOT_READY = "Not Ready"


class ComplianceStatus(str, Enum):
    PASS    = "PASS"
    WARNING = "WARNING"
    FAIL    = "FAIL"


@dataclass
class ReviewIssue:
    rule_id:          str
    severity:         Severity
    description:      str
    recommendation:   str
    affected_section: str

    def to_dict(self) -> dict:
        return {
            "rule_id":          self.rule_id,
            "severity":         self.severity.value,
            "description":      self.description,
            "recommendation":   self.recommendation,
            "affected_section": self.affected_section,
        }


@dataclass
class ComplianceCheck:
    regulation:  str
    status:      ComplianceStatus
    explanation: str

    def to_dict(self) -> dict:
        return {
            "regulation":  self.regulation,
            "status":      self.status.value,
            "explanation": self.explanation,
        }


@dataclass
class CategoryScores:
    document_structure:    float = 0.0
    regulatory_compliance: float = 0.0
    technical_content:     float = 0.0
    equipment_information: float = 0.0
    formatting:            float = 0.0
    completeness:          float = 0.0

    # Maximum points per category (must sum to 100)
    MAX_STRUCTURE:    float = 20.0
    MAX_REGULATORY:   float = 20.0
    MAX_TECHNICAL:    float = 20.0
    MAX_EQUIPMENT:    float = 15.0
    MAX_FORMATTING:   float = 15.0
    MAX_COMPLETENESS: float = 10.0

    def total(self) -> float:
        return (
            self.document_structure
            + self.regulatory_compliance
            + self.technical_content
            + self.equipment_information
            + self.formatting
            + self.completeness
        )

    def to_dict(self) -> dict:
        return {
            "document_structure":    round(self.document_structure, 1),
            "regulatory_compliance": round(self.regulatory_compliance, 1),
            "technical_content":     round(self.technical_content, 1),
            "equipment_information": round(self.equipment_information, 1),
            "formatting":            round(self.formatting, 1),
            "completeness":          round(self.completeness, 1),
        }


@dataclass
class ReviewResult:
    overall_score:          float         = 0.0
    readiness:              ReadinessLevel = ReadinessLevel.NOT_READY
    category_scores:        CategoryScores = field(default_factory=CategoryScores)
    issues:                 List[ReviewIssue]    = field(default_factory=list)
    recommendations:        List[str]            = field(default_factory=list)
    compliance:             List[ComplianceCheck] = field(default_factory=list)
    reviewer_comments:      str = ""
    approval_recommendation: str = ""
    doc_type:               str = ""

    def to_dict(self) -> dict:
        return {
            "overall_score":           round(self.overall_score, 1),
            "readiness":               self.readiness.value,
            "category_scores":         self.category_scores.to_dict(),
            "issues":                  [i.to_dict() for i in self.issues],
            "recommendations":         self.recommendations,
            "compliance":              [c.to_dict() for c in self.compliance],
            "reviewer_comments":       self.reviewer_comments,
            "approval_recommendation": self.approval_recommendation,
            "doc_type":                self.doc_type,
            "issue_summary": {
                "critical":    sum(1 for i in self.issues if i.severity == Severity.CRITICAL),
                "major":       sum(1 for i in self.issues if i.severity == Severity.MAJOR),
                "minor":       sum(1 for i in self.issues if i.severity == Severity.MINOR),
                "observation": sum(1 for i in self.issues if i.severity == Severity.OBSERVATION),
            },
        }
