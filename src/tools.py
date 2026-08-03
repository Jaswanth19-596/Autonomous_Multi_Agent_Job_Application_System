from langchain.tools import tool
import os
import shutil

@tool
def list_files(path: str):
    """
    List files in a directory
    """
    print(f"called the List files tool: {path}", end='\n')

    try:
        response = os.listdir(path)

    except Exception as e:
        print(e)
        return f"Raised an exception : Wrong path {e}"

    return response


@tool
def create_folder(path: str,folder_name: str):
    """
    Used to create a new folder
    """
    
    print(f"Called the Create Folder tool: {folder_name}", end = '\n')

    try:
        os.chdir(path)
        os.mkdir(folder_name)
    except Exception as e:

        return f"Exception while creating a folder : {e}"

    return f"created_folder : {folder_name} in path {path}"

@tool
def move_file(source_path: str, destination_path: str):
    """
    Used to move files from source to destination
    """
    print(f"Called the Move File tool : {source_path} to {destination_path}", end = '\n')

    try:
        shutil.move(source_path, destination_path)
    except Exception as e:
        print(e)
        return f"Error while moving file : {e}"

    return f"Moved file from {source_path} to {destination_path}"


@tool
def read_file(file_path : str):
    """
    Used to read the file content
    """
    print(f"Called Read File Tool: {file_path}")
    try:
        with open(file_path) as f:
            content = f.read()
        
        return content
    except Exception as e:
        return f"Exception while reading the file : {e}"


@tool 
def change_directory(directory_path: str):
    """
    Used to change the directory
    """
    print(f"Called Change Directory : {directory_path}")
    try:
        os.chdir(directory_path)
        return f"Changed the directory to {directory_path}"
    except Exception as e:
        return f"Exception while changing directory : {e}"
