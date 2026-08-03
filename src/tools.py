from langchain.tools import tool
import os
import shutil

@tool
def list_files(path: str):
    """
    List files in a directory
    """
    print("\n\n")
    print("called the List files tool")
    print("\n\n")

    try:
        response = os.listdir(path)

    except Exception as e:
        print(e)
        return f"Raised an exception : Wrong path {e}"

    print("Response of tool: ", response)
    return response


@tool
def create_folder(path: str,folder_name: str):
    """
    Used to create a new folder
    """
    print("\n\n")
    print("called the Create Folder tool")
    print("\n\n")
    os.chdir(path)
    os.mkdir(folder_name)

    return "created_folder"

@tool
def move_file(source_path: str, destination_path: str):
    """
    Used to move files from source to destination
    """
    print("\n\n")
    print("called the Move File tool")
    print("\n\n")

    try:

        shutil.move(source_path, destination_path)

    except Exception as e:
        print(e)
        return f"Error while moving file : {e}"

    return f"Moved file from {source_path} to {destination_path}"