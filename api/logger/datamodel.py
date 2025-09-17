from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator



class LangFuseTraceAttributes(BaseModel):
    """Langfuse trace-level attributes model"""
    
    name: str = Field(
        None,
        serialization_alias="langfuse.trace.name",
        description="The name of the trace",
    )
    
    user_id: str | None = Field(
        None,
        serialization_alias="langfuse.user.id",
        description="The unique identifier for the end-user",
    )
    
    session_id: str | None = Field(
        None,
        serialization_alias="langfuse.session.id",
        description="The unique identifier for the user session",
    )
    
    release: str | None = Field(
        None,
        serialization_alias="langfuse.release",
        description="The release version of your application",
    )
    
    public: bool | None = Field(
        None,
        serialization_alias="langfuse.trace.public",
        description="A boolean flag to mark a trace as public",
    )
    
    tags: list[str] | None = Field(
        None,
        serialization_alias="langfuse.trace.tags",
        description="An array of strings to categorize or label the trace",
    )
    
    metadata: dict[str, Any] | None = Field(
        None,
        serialization_alias="langfuse.trace.metadata",
        description="A flexible object for storing any additional, unstructured data on the trace",
    )
    
    input: Any | None = Field(
        None,
        serialization_alias="langfuse.trace.input",
        description="The initial input for the entire trace",
    )
    
    output: Any | None = Field(
        None,
        serialization_alias="langfuse.trace.output",
        description="The final output for the entire trace",
    )

class LangFuseSpanAttributes(BaseModel):
    """Langfuse observation-level attributes model"""
    
    observation_type: Literal["span", "generation", "event"] | None = Field(
        None,
        serialization_alias="langfuse.observation.type",
        description="The type of observation",
    )
    
    level: Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"] | None = Field(
        None,
        serialization_alias="langfuse.observation.level",
        description="The severity level of the observation",
    )
    
    status_message: str | None = Field(
        None,
        serialization_alias="langfuse.observation.status_message",
        description="A message describing the status of the observation",
    )
    
    metadata: dict[str, Any] | None = Field(
        None,
        serialization_alias="langfuse.observation.metadata",
        description="A flexible object for storing any additional, unstructured data on the observation",
    )
    
    input: Any | None = Field(
        None,
        serialization_alias="langfuse.observation.input",
        description="The input data for this specific observation",
    )
    
    output: Any | None = Field(
        None,
        serialization_alias="langfuse.observation.output",
        description="The output data from this specific observation",
    )
    
    model_name: str | None = Field(
        None,
        serialization_alias="langfuse.observation.model.name",
        description="The name of the generative model used",
    )
    
    model_parameters: dict[str, str | int] | None = Field(
        None,
        serialization_alias="langfuse.observation.model.parameters",
        description="Key-value pairs representing the settings used for the model invocation",
    )
    
    usage_details: dict[str, int] | None = Field(
        None,
        serialization_alias="langfuse.observation.usage_details",
        description="An object detailing the token counts for the generation",
    )
    
    cost_details: dict[str, float] | None = Field(
        None,
        serialization_alias="langfuse.observation.cost_details",
        description="The calculated cost of the generation in USD",
    )
    
    prompt_name: str | None = Field(
        None,
        serialization_alias="langfuse.observation.prompt.name",
        description="The name of a versioned prompt managed in Langfuse",
    )
    
    prompt_version: int | None = Field(
        None,
        serialization_alias="langfuse.observation.prompt.version",
        description="The version of the prompt",
    )
    
    completion_start_time: str | None = Field(
        None,
        serialization_alias="langfuse.observation.completion_start_time",
        description="The timestamp for when the model began generating the completion",
    )
    
    version: str | None = Field(
        None,
        serialization_alias="langfuse.version",
        description="The version of the observation",
    )
    
    environment: str | None = Field(
        None,
        serialization_alias="langfuse.environment",
        description="The deployment environment where the observation was generated",
    )

    @field_validator("completion_start_time")
    @classmethod
    def validate_completion_start_time(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("completion_start_time must be in ISO 8601 format")

    @model_validator(mode="after")
    def validate_observation_type_with_model(self) -> "LangFuseSpanAttributes":
        if self.model_name is not None and self.observation_type != "generation":
            raise ValueError(
                "observation_type must be 'generation' when model_name is present"
            )
        return self