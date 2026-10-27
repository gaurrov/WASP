from enum import StrEnum


class UserRole(StrEnum):
    INSTITUTION = "institution"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    CLARIFICATION_REQUESTED = "clarification_requested"
    READY_FOR_DECISION = "ready_for_decision"
    APPROVED = "approved"
    REJECTED = "rejected"


class DocumentType(StrEnum):
    FACULTY_LIST = "faculty_list"
    QUALIFICATION_CERTIFICATE = "qualification_certificate"
    APPOINTMENT_LETTER = "appointment_letter"
    FIRE_NOC = "fire_noc"
    BUILDING_CERTIFICATE = "building_certificate"
    LAND_DOCUMENT = "land_document"
    LAB_INVENTORY = "lab_inventory"
    OTHER = "other"
    UNCLASSIFIED = "unclassified"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class FindingStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"
    NOT_APPLICABLE = "not_applicable"
    UNABLE_TO_DETERMINE = "unable_to_determine"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RuleStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    RETIRED = "retired"


class ReviewOutcome(StrEnum):
    CONFIRM = "confirm"
    OVERRIDE = "override"
    REQUEST_CLARIFICATION = "request_clarification"
    ESCALATE = "escalate"


class AlertStatus(StrEnum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    ACTION_PENDING = "action_pending"
    OVERDUE = "overdue"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    REOPENED = "reopened"
