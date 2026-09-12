from pydantic import BaseModel, Field
from datetime import datetime
class Citation(BaseModel):
    file: str = Field(
        description="Relative path to the csv file, e.g 'syslog.csv'"
    )
    quotes: str = Field(
        description="Exact line(s) from the file that support the claim."
    )


class SearchAnswer(BaseModel):
    answer: str = Field(description="The answer in plain English")
    citations: list[Citation] = Field(
        description="Files and quotes that support the answer"
    )

class LogExpectedFormat(BaseModel):
    timestamp: datetime
    source: str
    event_type: str
    message: str
    raw_line: str
