from pydantic import BaseModel #type: ignore


class Chart(BaseModel):
    title: str
    chart_type: str
    x_axis: str
    y_axis: str