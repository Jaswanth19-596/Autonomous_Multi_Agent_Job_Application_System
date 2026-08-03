from langchain_openrouter import ChatOpenRouter
from src.tools import list_files, move_file, create_folder
import os
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

load_dotenv()

model = ChatOpenRouter(
    model = "minimax/minimax-m3",
    api_key = os.environ["OPENROUTER_API_KEY"]
)

tools = [
    list_files,
    move_file,
    create_folder
]

tools_by_name = {
    "list_files": list_files,
    "move_file": move_file,
    "create_folder": create_folder
}

model_with_tools = model.bind_tools(tools)


def read_folder_path(state):
    print("Entering into Read Folder Node")
    folder_path = input("Enter the folder path: ")

    return {"messages": [HumanMessage(content=folder_path)]}

def file_organizer_node(state):
    print("Entering into File organizer Node")
    response = model_with_tools.invoke(state["messages"])

    return {"messages": [response]}


def tool_node(state):
    print("Entering into Tool Node")

    previous_response = state['messages'][-1]

    tool_responses = []

    for tool_call in previous_response.tool_calls:

        if tool_call["name"] not in tools_by_name:
            raise Exception("Invalid tool call")

        tool = tools_by_name[tool_call["name"]]

        result = tool.invoke(tool_call["args"])

        tool_responses.append(
            ToolMessage(
                content = str(result),
                tool_call_id = tool_call["id"]
            )
        )

    return {"messages": tool_responses}
    




    

