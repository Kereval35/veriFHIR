from pydantic import BaseModel
from typing import List, Optional, TypeVar, Type


T = TypeVar("T", bound="BaseSchemaModel")

class BaseSchemaModel(BaseModel):
    @classmethod
    def get_response_format(cls: Type[T], name: str) -> dict:
        return {
            'type': 'json_schema',
            'json_schema': {
                'name': name,
                'schema': cls.model_json_schema(),
            }
        }


class TextCheckResponse(BaseSchemaModel):
    id: str
    extract: Optional[str]

class TextCheckResponses(BaseSchemaModel):
    responses: List[TextCheckResponse]

class ComparativeArtifactsCheckResponse(BaseSchemaModel):
    narrative: str
    formal: Optional[str]

class ComparativeArtifactsCheckResponses(BaseSchemaModel):
    responses: List[ComparativeArtifactsCheckResponse]