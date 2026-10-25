from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class AuthRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
class AuthResponse(BaseModel):
    user_id: str
    token: str
class TopicCreate(BaseModel):
    name: str
    description: str
    estimated_minutes: int
    content_url: str | None = None
class EdgeCreate(BaseModel):
    prerequisite_id: str
    topic_id: str
class ResponseCreate(BaseModel):
    question_id: str
    selected_choice_index: int
class QuestionPublic(BaseModel):
    id: str
    topic_id: str
    prompt: str
    choices: list[str]
class MasteryPublic(BaseModel):
    topic_id: str
    topic_name: str
    p_mastery: float
    last_updated: datetime
    source: str

class LabBKTRequest(BaseModel):
    prior_mastery: float = Field(ge=0, le=1)
    correct: bool
    p_transit: float | None = Field(default=None, ge=0, le=1)
    p_slip: float | None = Field(default=None, ge=0, le=1)
    p_guess: float | None = Field(default=None, ge=0, le=1)

class LabSearchRequest(BaseModel):
    target_topic_id: str
    start_topic_id: str | None = None

class LabDemoStepRequest(LabSearchRequest):
    topic_id: str
    correct: bool | None = None
    question_id: str | None = None
    selected_choice_index: int | None = Field(default=None, ge=0)
    mastery: dict[str, float] = Field(default_factory=dict)

    @field_validator('mastery')
    @classmethod
    def mastery_values_are_probabilities(cls, value):
        if any(not 0 <= probability <= 1 for probability in value.values()):
            raise ValueError('synthetic mastery values must be between 0 and 1')
        return value

    @model_validator(mode='after')
    def validate_demo_answer(self):
        if self.question_id:
            if self.selected_choice_index is None or self.correct is not None:
                raise ValueError('provide a question_id and selected_choice_index, or provide correct for a controlled demo')
        elif self.correct is None:
            raise ValueError('a controlled demo step requires correct or a quiz answer')
        return self
