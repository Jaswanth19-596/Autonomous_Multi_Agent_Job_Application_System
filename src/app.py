from langgraph.graph import StateGraph, START, END, MessagesState
from typing import TypedDict
from src.nodes import read_folder_path, file_organizer_node, tool_node
from langchain_core.messages import SystemMessage

class State(TypedDict, total = False):
    folder_path : str


graph = StateGraph(MessagesState)


def condition(state):
    if state['messages'][-1].tool_calls:
        return "tools"
    return "END"

graph.add_node(read_folder_path)
graph.add_node(file_organizer_node)
graph.add_node(tool_node)

graph.add_edge(START, "read_folder_path")
graph.add_edge("read_folder_path", "file_organizer_node")
graph.add_conditional_edges("file_organizer_node", condition, {"tools": "tool_node","END": END})
graph.add_edge("tool_node", "file_organizer_node")


graph = graph.compile()

graph.invoke({
    "messages": [
        SystemMessage(content = """You are an file organizing agent, and you have been given some tools, only use those tools 
        to organize the files. The user is too lazy to do it by himself, so he is giving you the 
        responsibility to do that. 

        You can either decide to classify the files using the names and extensions of the files or you can also use the read_file tool
        to read the contents of the file to get better idea about the file. This gives you more information on how to classify the file. 

        If the folder that you are working with has subfolders, you also need to organize the subfolders as well. 
        you can use the tools to move in and out of folders. 

        And I also want you to identify the unnecessary files and create a folder called can_delete and add those all unnecessary files into that folder. 
        This is not an universal folder, it should be present for a specific sub project. 

        use the provided tools and call one of the tools if you require. 
    """)
    ]
})

