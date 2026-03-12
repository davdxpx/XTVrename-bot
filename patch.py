import re

with open("plugins/flow.py", "r") as f:
    content = f.read()

# Identify the block of state checks we need to move
start_marker = '    if state == "awaiting_general_file":'
end_marker = '    if not Config.PUBLIC_MODE:'

if start_marker in content and end_marker in content:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    # Extract the block
    block_to_move = content[start_idx:end_idx]

    # Remove it from the original position
    content = content[:start_idx] + content[end_idx:]

    # Find the end of the rate limit check
    insert_marker = '    # Pre-check file size limits before processing'
    insert_idx = content.find(insert_marker)

    if insert_idx != -1:
        # Insert the block
        new_content = content[:insert_idx] + block_to_move + "\n" + content[insert_idx:]

        with open("plugins/flow.py", "w") as f:
            f.write(new_content)
        print("Successfully moved the block.")
    else:
        print("Could not find insert marker.")
else:
    print("Could not find markers.")
