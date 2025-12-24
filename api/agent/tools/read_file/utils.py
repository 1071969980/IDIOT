from io import StringIO

def read_from_string(string: str, offset: int = 0, limit: int = 1000, add_line_numbers: bool = True):
    file_like = StringIO(string)

    if offset > 0:
        for i in range(offset):
            file_like.readline()
    
    formatted_lines = []
    for i in range(offset, offset+limit):
        line = file_like.readline()
        if len(line) > 1000:
            line = line[:1000] + "... [line be truncated] \n"
        
        if add_line_numbers:
            line = (f"{i}→").rjust(5, " ") + line
        formatted_lines.append(line)

    return "".join(formatted_lines)