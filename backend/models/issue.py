from pydantic import BaseModel
from typing import Optional, List

class Issue(BaseModel):
    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    root_cause: Optional[str] = None
    severity: Optional[str] = None
    affected_files: Optional[List[str]] = []
    original_finding: Optional[dict] = None