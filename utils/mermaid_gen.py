def generate_mermaid(file_tree, max_depth=3):
    """
    Generates robust Mermaid code from the project file tree.
    
    Args:
        file_tree: Project structure data (dict) passed directly
        max_depth: Maximum traversal depth (default: 3)
    
    Returns:
        String containing the Mermaid diagram code
    """
    lines = [
        "graph LR",
        "    %% Style Definitions",
        "    classDef folder fill:#2d333b,stroke:#adbac7,stroke-width:2px,color:#adbac7",
        "    classDef file fill:#22272e,stroke:#444c56,color:#768390"
    ]
    lines.append("    root[\"📂 Project Root\"]:::folder")
    
    def traverse(node, parent_id="root", current_depth=0):
        if current_depth >= max_depth:
            return

        # Sort to display folders first, then files (professional aesthetics)
        items = sorted(node.items(), key=lambda x: "type" in x[1])

        for name, content in items:
            # Create a clean unique ID based on relative path to avoid collisions
            rel_path = content.get("rel_path", name)
            node_id = "".join(c for c in rel_path if c.isalnum()).lower()
            
            if "type" in content:  # It's a FILE
                lines.append(f'    {parent_id} --> {node_id}("📄 {name}"):::file')
            else:  # It's a DIRECTORY
                lines.append(f'    {parent_id} --> {node_id}["📂 {name}"]:::folder')
                # Recurse into children
                traverse(content, node_id, current_depth + 1)

    traverse(file_tree)
    return "\n".join(lines)
