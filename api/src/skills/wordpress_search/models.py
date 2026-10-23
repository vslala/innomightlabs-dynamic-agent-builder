from pydantic import BaseModel, PositiveInt


class ReadPostRequest(BaseModel):
    id: PositiveInt
