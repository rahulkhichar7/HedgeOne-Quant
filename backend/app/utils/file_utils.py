import os
from typing import List 

def directory_traverse(
    root_path,
    skip_folders:List[str] = ["__pycache__"],
    skip_files:List[str] = [".env"],
    indent=""
):
    if skip_folders is None:
        skip_folders = set()
    if skip_files is None:
        skip_files = set()

    # Convert to sets for O(1) lookup
    skip_folders = set(skip_folders)
    skip_files = set(skip_files)

    try:
        items = sorted(os.listdir(root_path))
    except PermissionError:
        print(f"{indent}⛔ Permission denied")
        return

    for item in items:
        item_path = os.path.join(root_path, item)

        # ----------- DIRECTORY -----------
        if os.path.isdir(item_path):
            if item in skip_folders:
                print(f"{indent}|----📁 {item} (skipped)")
                continue

            print(f"{indent}|----📁 {item}")
            directory_traverse(
                item_path,
                skip_folders,
                skip_files,
                indent + "     "
            )

        # ----------- FILE -----------
        else:
            if item in skip_files:
                print(f"{indent}|----📄 {item} (skipped)")
                continue

            print(f"{indent}|----📄 {item}")

            # Read only text-like files
            if item.endswith((".py", ".txt", ".md", ".json", ".yaml", ".yml")):
                try:
                    with open(item_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    content_indent = indent + "     "
                    print(f"{content_indent}|- 📜 Content of {item}:")
                    for line in content.splitlines():
                        print(f"{content_indent}   {line}")

                except Exception as e:
                    print(f"{indent}     ⚠️ Cannot read file: {e}")
