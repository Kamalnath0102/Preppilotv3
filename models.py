from pydantic import BaseModel, Field


class Question(BaseModel):
    question: str
    topic: str
    difficulty: int = Field(ge=1, le=5)
    key_points: list[str] = Field(min_length=2, max_length=6)  # hidden rubric


class Score(BaseModel):
    correctness: int = Field(ge=1, le=5)
    depth: int = Field(ge=1, le=5)
    communication: int = Field(ge=1, le=5)
    feedback: str
    missed_points: list[str] = []
    follow_up: str = ""  # one probing question about the candidate's own answer


class FollowScore(BaseModel):
    quality: int = Field(ge=1, le=5)
    feedback: str


class DayPlan(BaseModel):
    day: int = Field(ge=1, le=7)
    focus: str
    tasks: list[str]


class Report(BaseModel):
    strengths: list[str]
    weaknesses: list[str]
    study_plan: list[DayPlan]
    encouragement: str
