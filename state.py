from typing import Annotated, Any, TypedDict
import operator
from langchain_core.messages import AnyMessage

class TravelState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    user_id: str  ### unique id
    user_query: str  ### user query 

    trip_constraints: dict[str, Any]  ## destination:, days:
    selected_agents: list[str]  ## selected agents: what agents are selected for action
    supervisor_reasoning: str  ## Why the agent was selected

    flight_results: str
    hotel_results: str
    weather_results: str
    budget_results: str
    itinerary: str

    approval_request: str  ## itenary agent draft the iternary and the llm will show the user
    human_feedback: str  ## user feedback
    approved: bool  ## yes/no

    final_response: str
    llm_calls: int  ## how many times the llm was called.