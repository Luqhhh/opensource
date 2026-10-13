from dataclasses import asdict, dataclass, field


@dataclass
class Example:
    id: str
    path: str
    start_line: int
    end_line: int
    code: str
    context: str


@dataclass
class Execution:
    status: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    oracle: str = "none"


@dataclass
class Proposal:
    code: str
    rationale: str
    provider: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_seconds: float = 0.0


@dataclass
class Result:
    example: Example
    before: Execution
    status: str
    proposal: Proposal | None = None
    after: Execution | None = None
    rejection: str | None = None
    diff: str | None = None

    def to_dict(self):
        return asdict(self)
