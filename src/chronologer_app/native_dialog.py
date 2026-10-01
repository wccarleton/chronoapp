"""Native file chooser helper, isolated so Tk owns its process's main thread."""
import json
import sys


def main():
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog

        options = json.loads(sys.stdin.read())
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        kwargs = dict(parent=root, title=options["title"],
                      filetypes=[("ChronoApp project", "*.chrono")])
        if options.get("directory"):
            kwargs["initialdir"] = options["directory"]
        if options["mode"] == "save":
            path = filedialog.asksaveasfilename(**kwargs, defaultextension=".chrono",
                                              initialfile=options["name"], confirmoverwrite=True)
        else:
            path = filedialog.askopenfilename(**kwargs)
        print(json.dumps({"path": path or None}))
    except Exception as error:
        print(json.dumps({"error": f"Native file dialog unavailable: {error}"}))
    finally:
        if root is not None:
            root.destroy()


if __name__ == "__main__":
    main()
