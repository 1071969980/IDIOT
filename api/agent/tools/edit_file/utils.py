

def edit_string(string: str, old_text: str, new_text: str, replace_all: bool = False):
    index = string.find(old_text)
    if index == -1:
        raise ValueError("old_text not found in string")
    
    has_second_occurrence = string.find(old_text, index + 1) != -1
    if not replace_all and has_second_occurrence:
        raise ValueError("old_text found more than once in string")
    
    return string.replace(old_text, new_text)
        
